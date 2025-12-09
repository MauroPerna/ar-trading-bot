import pandas as pd
import logging
from typing import List, Dict

from src.domain.etl.dtos.enriched_data import EnrichedData
from src.domain.etl.dtos.extracted_data import ExtractedData
from src.domain.etl.calculators.basic_indicators_calculator import IndicatorCalculator

logger = logging.getLogger(__name__)


class EnricherService:
    """
    TRANSFORM: Pipeline completo de transformación técnica
    Stage 1: Indicadores matemáticos (pandas-ta)
    Stage 2: Analizadores custom 
    Stage 3: Validación y limpieza
    """

    def __init__(self) -> None:
        # Stage 1: Mathematical indicators
        self.indicator_calculator_cls = IndicatorCalculator

        # Stage 2: Custom analyzers (nombre_corto, módulo, clase)
        self.analyzers = [
            ("slope", "src.domain.etl.analyzers.trend_analyzer", "TrendAnalyzer"),
            ("fvg", "src.domain.etl.analyzers.fair_value_gap_analyzer",
             "FairValueGapAnalyzer"),
            ("breakout", "src.domain.etl.analyzers.breakout_analyzer",
             "BreakoutAnalyzer"),
        ]

    def transform(self, extracted_data: ExtractedData, indicators: List[str]) -> EnrichedData:
        """Pipeline principal de transformación."""
        logger.info(
            f"🔧 TRANSFORM: Starting transformation pipeline, for the next indicators: {', '.join(indicators)}"
        )

        transformation_log: Dict[str, List[str]] = {
            "stages_completed": [],
            "indicators_added": [],
            "analyzers_applied": [],
            "errors": [],
            "warnings": [],
        }

        df = extracted_data.ohlcv.copy()
        original_columns = len(df.columns)

        try:
            # Stage 1: Apply mathematical indicators
            df = self._stage_1_mathematical_indicators(
                df, indicators, transformation_log)

            # Stage 2: Apply custom analyzers
            df = self._normalize_columns(df)
            df = self._stage_2_custom_analyzers(
                df, indicators, timeframe=extracted_data.timeframe, transformation_log=transformation_log
            )

            # Stage 3: Validation and cleanup
            df = self._stage_3_validation(df, transformation_log)

            final_columns = len(df.columns)

            logger.info(
                f"✅ TRANSFORM completed: {original_columns}→{final_columns} columns")

            metadata = {
                **extracted_data.metadata,
                "timeframe": extracted_data.timeframe,
            }

            return EnrichedData(
                ohlcv=df,
                metadata=metadata,
                asset=extracted_data.asset,
                timeframe=extracted_data.timeframe,
                transformation_log=transformation_log,
                indicators_added=transformation_log["indicators_added"],
            )

        except Exception as e:
            logger.error(f"❌ TRANSFORM failed: {e}")
            transformation_log["errors"].append(str(e))
            raise

    def _stage_1_mathematical_indicators(
        self,
        df: pd.DataFrame,
        indicators: List[str],
        transformation_log: Dict[str, List[str]],
    ) -> pd.DataFrame:
        """Stage 1: Apply ALL pandas-ta indicators."""
        logger.info("📊 Stage 1: Applying mathematical indicators (pandas-ta)")

        try:
            calc = self.indicator_calculator_cls(df)
            df_with_indicators = calc.apply(indicators=indicators)

            new_columns = set(df_with_indicators.columns) - set(df.columns)
            transformation_log["indicators_added"].extend(list(new_columns))
            transformation_log["stages_completed"].append(
                "mathematical_indicators")

            logger.info(
                f"✅ Stage 1 completed: {len(new_columns)} indicators added")
            return df_with_indicators

        except Exception as e:
            error_msg = f"Stage 1 failed: {e}"
            logger.error(f"❌ {error_msg}")
            transformation_log["errors"].append(error_msg)
            return df

    def _stage_2_custom_analyzers(
        self,
        df: pd.DataFrame,
        indicators: List[str],
        timeframe: str,
        transformation_log: Dict[str, List[str]],
    ) -> pd.DataFrame:
        """Stage 2: Apply custom analyzers sequentially."""
        logger.info("🧠 Stage 2: Applying custom analyzers")

        current_df = df.copy()

        for analyzer_name, module_path, class_name in self.analyzers:
            # Usamos el mismo parámetro "indicators" como filtro, por ahora.
            if indicators and analyzer_name not in indicators:
                logger.info(
                    f"⏩ Skipping analyzer '{analyzer_name}' (not in indicators)")
                continue

            try:
                current_df = self._apply_single_analyzer(
                    current_df,
                    analyzer_name,
                    module_path,
                    class_name,
                    timeframe=timeframe,
                )
                transformation_log["analyzers_applied"].append(analyzer_name)

            except Exception as e:
                warning_msg = f"{class_name} failed: {e}"
                logger.warning(f"⚠️ {warning_msg}")
                transformation_log["warnings"].append(warning_msg)

        transformation_log["stages_completed"].append("custom_analyzers")
        logger.info(
            f"✅ Stage 2 completed: {len(transformation_log['analyzers_applied'])} analyzers applied"
        )
        return current_df

    def _apply_single_analyzer(self, df: pd.DataFrame, name: str, module_path: str, class_name: str, timeframe) -> pd.DataFrame:
        """Apply a single analyzer with error handling"""
        logger.info(f"🔍 Applying {class_name}...")

        try:
            module = __import__(module_path, fromlist=[class_name])
            analyzer_class = getattr(module, class_name)

            if class_name == 'BreakoutAnalyzer':
                result_df = analyzer_class(
                    df, timeframe=timeframe).analyze()
                logger.info(f"✅ {class_name} completed")
                return result_df
            else:
                result_df = analyzer_class(df).analyze()
                logger.info(f"✅ {class_name} completed")
                return result_df

        except ImportError as e:
            raise Exception(f"Could not import {class_name}: {e}")
        except Exception as e:
            raise Exception(f"Error running {class_name}: {e}")

    def _stage_3_validation(
        self,
        df: pd.DataFrame,
        transformation_log: Dict[str, List[str]],
    ) -> pd.DataFrame:
        """Stage 3: Data validation and cleanup."""
        logger.info("🧹 Stage 3: Validation and cleanup")

        original_length = len(df)

        try:
            df = self._validate_data_quality(df)
            df = self._handle_missing_values(df)
            df = self._validate_indicator_ranges(df, transformation_log)

            final_length = len(df)
            if final_length != original_length:
                warning_msg = f"DataFrame length changed: {original_length}→{final_length}"
                logger.warning(f"⚠️ {warning_msg}")
                transformation_log["warnings"].append(warning_msg)

            transformation_log["stages_completed"].append("validation")
            logger.info("✅ Stage 3 completed")
            return df

        except Exception as e:
            error_msg = f"Stage 3 failed: {e}"
            logger.error(f"❌ {error_msg}")
            transformation_log["errors"].append(error_msg)
            return df

    def _validate_indicator_ranges(
        self,
        df: pd.DataFrame,
        transformation_log: Dict[str, List[str]],
    ) -> pd.DataFrame:
        """Validate ranges of known indicators"""
        validations = {
            'RSI_14': (0, 100, 'RSI debe estar entre 0-100'),
            'WILLR_14': (-100, 0, 'Williams %R debe estar entre -100-0'),
            'CCI_20': (-1000, 1000, 'CCI debe estar entre -1000-1000'),
            'STOCHk_14_3_3': (0, 100, 'Stochastic %K debe estar entre 0-100'),
            'STOCHd_14_3_3': (0, 100, 'Stochastic %D debe estar entre 0-100'),
            'MACD_12_26_9': (-1e6, 1e6, 'MACD valores extremos'),
            'MACDh_12_26_9': (-1e6, 1e6, 'MACD Histogram valores extremos'),
            'ADX_14': (0, 100, 'ADX debe estar entre 0-100'),
            'ATR_14': (0, 1e6, 'ATR valores negativos o extremadamente altos'),
        }

        for column, (min_val, max_val, message) in validations.items():
            if column in df.columns:
                invalid_mask = (df[column] < min_val) | (df[column] > max_val)
                if invalid_mask.any():
                    warning_msg = f"Out of range values in {column}: {message}"
                    logger.warning(f"⚠️ {warning_msg}")
                    transformation_log['warnings'].append(warning_msg)
                    df.loc[invalid_mask, column] = pd.NA

        return df

    def _validate_data_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        """Basic data quality validations"""
        # Remove duplicates
        original_len = len(df)
        df = df.drop_duplicates()
        if len(df) != original_len:
            logger.info(f"🧹 Removed {original_len - len(df)} duplicates")

        # Ensure we have basic OHLCV columns
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing_columns = [
            col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing columns: {missing_columns}")

        return df

    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        price_columns = ['Open', 'High', 'Low', 'Close']
        df[price_columns] = df[price_columns].ffill()

        if 'Volume' in df.columns:
            df['Volume'] = df['Volume'].ffill()

        zone_cols = [c for c in df.columns
                     if c.startswith("zone_support_") or c.startswith("zone_resistance_")]
        main_cols = ["main_support", "main_resistance"]

        indicator_columns = [c for c in df.columns
                             if c not in (price_columns + ['Volume'] + zone_cols + main_cols)]

        for col in indicator_columns:
            first_valid = df[col].first_valid_index()
            if first_valid is not None:
                mask = df.index >= first_valid
                df.loc[mask, col] = df.loc[mask, col].ffill()

        return df

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Only normalize column names - NO indicators"""
        return df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })
