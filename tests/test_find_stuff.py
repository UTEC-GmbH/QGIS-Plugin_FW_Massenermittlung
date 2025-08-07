import sys

from qgis.core import QgsProject, QgsVectorLayer
from qgis.testing import start_app, unittest

from ..modules.find_stuff import find_unconnected_endpoints
from ..modules.general import LayerManager

# Start the QGIS application
start_app()


class TestFindUnconnectedEndpoints(unittest.TestCase):
    def setUp(self):
        """Set up the test case."""
        # Path to the QGIS project file
        # Please replace this with the actual path to your project file
        self.project_path = "C:\\Users\\fl\\Documents\\Python\\QGIS-Plugin_FW_Massenermittlung - Beispeilprojekt\\Beispeilprojekt_Massenermittlung.qgz"

        # Name of the layer to test
        # Please replace this with the actual name of your layer
        self.layer_name = "250625_938_Hahle_Net"

        # Load the QGIS project
        self.project = QgsProject.instance()
        self.project.read(self.project_path)

        # Get the layer to be tested
        self.layer = self.project.mapLayersByName(self.layer_name)[0]

        # Create a new layer for the results
        self.new_layer = QgsVectorLayer("Point?crs=25832", "test_results", "memory")

        # Create a LayerManager object
        self.layer_manager = LayerManager(self.layer, self.new_layer)

    def tearDown(self):
        """Tear down the test case."""
        # Close the QGIS project
        self.project.clear()

    def test_find_unconnected_endpoints(self):
        """Test the find_unconnected_endpoints function."""
        # Call the function to be tested
        find_unconnected_endpoints(self.layer_manager)

        # Check that the correct number of points were added to the new layer
        self.assertEqual(self.new_layer.featureCount(), 339)


if __name__ == "__main__":
    unittest.main()
