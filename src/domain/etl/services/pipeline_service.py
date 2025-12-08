from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from src.domain.etl.dtos.enriched_data import EnrichedData
from src.domain.etl.dtos.extracted_data import ExtractedData
from src.domain.etl.services.extractor_service import ExtractorService
from src.domain.etl.services.enricher_service import EnricherService


class FeaturePipelineService:
    """
    Orquesta:
      1) EXTRACT (raw OHLCV por símbolo)
      2) ENRICH (indicadores técnicos + analyzers)

    Puede trabajar:
      - con un solo símbolo → devuelve EnrichedData
      - con varios símbolos → devuelve dict[symbol, EnrichedData]
    """

    def __init__(self, extractor: ExtractorService, transformer: EnricherService):
        self.extractor = extractor
        self.transformer = transformer

    async def start(
        self,
        symbols: Optional[Union[str, List[str]]] = None,
        indicators: Optional[List[str]] = [],
        timeframe: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Union[EnrichedData, Dict[str, EnrichedData]]:
        """
        Ejecuta el pipeline completo.

        symbols:
          - None → usa todos los default_symbols del YFinanceService
          - "AAPL.BA" → solo ese
          - ["AAPL.BA", "TSLA.BA"] → varios
        """
        raw_data = await self.extractor.extract(symbols, timeframe=timeframe, start=start, end=end)

        if isinstance(raw_data, ExtractedData):
            enriched = self.transformer.transform(raw_data, indicators)
            return enriched

        results: Dict[str, EnrichedData] = {}
        for sym, extracted in raw_data.items():
            results[sym] = self.transformer.transform(extracted, indicators)

        return results
