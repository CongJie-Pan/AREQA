import pytest
import os
import tempfile
import shutil

@pytest.fixture(autouse=True, scope="function")
def isolate_gum_data_directory():
    """
    Automatically intercept any tests that initialize GUM and force them
    to use a temporary directory instead of the real ~/.cache/gum.
    """
    temp_dir = tempfile.mkdtemp(prefix="gum_test_env_")
    
    # Store the original environment variable if it exists
    original_data_dir = os.environ.get("GUM_TEST_DATA_DIR")
    
    # Force the backend to use the temp directory
    os.environ["GUM_TEST_DATA_DIR"] = temp_dir
    
    yield
    
    # Restore the original state
    if original_data_dir is not None:
        os.environ["GUM_TEST_DATA_DIR"] = original_data_dir
    else:
        del os.environ["GUM_TEST_DATA_DIR"]
        
    # Cleanup the temporary directory to avoid taking up disk space
    shutil.rmtree(temp_dir, ignore_errors=True)
