"""Hybrid PII detection using Presidio patterns and spaCy named entities."""

from importlib.metadata import version

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    CreditCardRecognizer,
    IpRecognizer,
    PhoneRecognizer,
    SpacyRecognizer,
    UsSsnRecognizer,
)

from guardrail_mini.core.policy_engine import PolicyAction, PolicyMetadata, PolicyResult


class PiiDetector:
    """Detect structured identifiers and common English named entities."""

    def __init__(self) -> None:
        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
        registry = RecognizerRegistry(supported_languages=["en"])
        email_recognizer = PatternRecognizer(
            supported_entity="EMAIL_ADDRESS",
            patterns=[
                Pattern(
                    "Email address",
                    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b",
                    0.85,
                )
            ],
            context=["email", "e-mail", "contact"],
            supported_language="en",
            name="LocalEmailRecognizer",
        )
        for recognizer in (
            SpacyRecognizer(),
            email_recognizer,
            PhoneRecognizer(),
            UsSsnRecognizer(),
            CreditCardRecognizer(),
            IpRecognizer(),
        ):
            registry.add_recognizer(recognizer)
        self._analyzer = AnalyzerEngine(
            registry=registry,
            nlp_engine=nlp_engine,
            supported_languages=["en"],
        )
        self.model_version = (
            f"presidio-analyzer@{version('presidio-analyzer')}+"
            f"en_core_web_sm@{version('en-core-web-sm')}"
        )

    def score(self, text: str) -> tuple[float, tuple[str, ...]]:
        """Return the maximum recognizer confidence and entity types only."""

        detections = self._analyzer.analyze(text=text, language="en")
        score = max((float(detection.score) for detection in detections), default=0.0)
        categories = tuple(sorted({str(detection.entity_type) for detection in detections}))
        return score, categories

    def warm_up(self) -> None:
        """Run a harmless sample through the NLP pipeline during startup."""

        self.score("This neutral startup sentence contains no private identifiers.")


class PiiPolicy:
    """Convert hybrid PII recognizer confidence into a policy outcome."""

    def __init__(
        self,
        detector: PiiDetector,
        threshold: float,
        review_threshold: float | None,
    ) -> None:
        if review_threshold is not None and review_threshold > threshold:
            raise ValueError("The PII review threshold must not exceed its block threshold.")
        self._detector = detector
        self._threshold = threshold
        self._review_threshold = review_threshold
        self.metadata = PolicyMetadata(
            id="pii",
            name="Personally identifiable information detection",
            version="1",
            threshold=threshold,
            review_threshold=review_threshold,
            severity=3,
        )

    def evaluate(self, text: str) -> PolicyResult:
        score, categories = self._detector.score(text)
        if score >= self._threshold:
            action = PolicyAction.BLOCK
        elif self._review_threshold is not None and score >= self._review_threshold:
            action = PolicyAction.REVIEW
        else:
            action = PolicyAction.ALLOW
        return PolicyResult(
            policy_id=self.metadata.id,
            score=score,
            threshold=self._threshold,
            action=action,
            model_version=self._detector.model_version,
            severity=self.metadata.severity,
            categories=categories,
        )


def load_pii_detector() -> PiiDetector:
    """Initialize local Presidio recognizers and the spaCy model."""

    detector = PiiDetector()
    detector.warm_up()
    return detector
