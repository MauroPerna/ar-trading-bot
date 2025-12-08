from enum import Enum


class Instruments(Enum):
    OPCIONES = "opciones"
    ACCIONES = "acciones"
    FUTUROS = "futuros"
    CEDEARS = "cedears"
    TITULOS_PUBLICOS = "titulosPublicos"
    ADRS = "aDRs"
    ON = "obligacionesNegociables"
    letras = "letras"


class Countries(Enum):
    ARGENTINA = "argentina"
    USA = "estados_Unidos"
