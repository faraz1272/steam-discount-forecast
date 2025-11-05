# src/steam_sale/exceptions.py

class SteamSaleError(Exception):
    """Base class for all custom exceptions in the Steam Sale project."""
    pass


class ModelNotLoadedError(SteamSaleError):
    """Raised when the model or its features have not been loaded."""
    pass


class BadRequestError(SteamSaleError):
    """Raised when input features are invalid or incomplete."""
    pass