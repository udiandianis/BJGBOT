import json
import subprocess
import sys
import unittest


class LightweightImportsTest(unittest.TestCase):
    def test_scheduler_and_data_queries_do_not_load_plotting_runtime(self):
        result = subprocess.run([sys.executable, '-c',
            "import json,sys; import src.services.scheduler; import src.services.statistics; "
            "print(json.dumps({'plotting_loaded': any(x == 'matplotlib' or x.startswith('matplotlib.') for x in sys.modules)}))"],
            capture_output=True, text=True, check=True)
        self.assertFalse(json.loads(result.stdout)['plotting_loaded'])
