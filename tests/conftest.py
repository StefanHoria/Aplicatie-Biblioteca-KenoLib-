import os
import sys

# Permite "import database", "import api_service" etc. din testele care
# rulează cu rădăcina proiectului ca working directory, indiferent de
# unde e pornit pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
