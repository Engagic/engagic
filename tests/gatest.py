import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.adapters.all_adapters import GranicusAdapter

# Configure logging FIRST before any imports that use loggers
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("engagic")

logger.info("fuck")

gatest = GranicusAdapter("acworth-ga")
results = gatest.upcoming_packets()

print(list(results))