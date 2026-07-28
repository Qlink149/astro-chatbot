from kisna_chatbot.pipelines.pipeline import Pipeline
from kisna_chatbot.processors.samara_reading_agent import SamaraReadingAgent


class SamaraPipeline(Pipeline):
    """Pipeline for the Samara Vedic astrology client."""

    def __init__(self) -> None:
        processors = [SamaraReadingAgent()]
        super().__init__(processors)
