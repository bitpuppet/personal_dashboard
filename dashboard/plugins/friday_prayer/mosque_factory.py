from typing import Dict, Optional
from .mosque_base import MosqueBase
from .mosques.sachse_islamic_center import SachseIslamicCenterMosque
from .mosques.east_plano import EastPlanoMosque
import logging

logger = logging.getLogger(__name__)

MOSQUE_TYPES = {
    'sachse_islamic_center': SachseIslamicCenterMosque,
    'east_plano': EastPlanoMosque
}

def create_mosque(mosque_type: str, config: Dict) -> Optional[MosqueBase]:
    """Create a mosque instance based on type"""
    try:
        mosque_class = MOSQUE_TYPES.get(mosque_type)
        if mosque_class:
            return mosque_class(config)
        else:
            logger.error(f"Unknown mosque type: {mosque_type}")
            return None
    except Exception as e:
        logger.error(f"Failed to create mosque {mosque_type}: {e}")
        return None 