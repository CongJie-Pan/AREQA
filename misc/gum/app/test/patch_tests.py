import re

with open("test_backend.py", "r") as f:
    content = f.read()

# We need to mock main.set_key for all tests so it doesn't overwrite .env
if "from unittest.mock import patch" not in content:
    content = "from unittest.mock import patch\n" + content

# Wrap the setup fixture to patch set_key globally during tests
fixture_replacement = """
@pytest_asyncio.fixture(autouse=True)
async def cleanup():
    # Setup
    with patch('main.set_key') as mock_set_key:
        yield
    # Teardown
    await gum_manager.stop_recording()
"""

content = re.sub(r'@pytest_asyncio\.fixture\(autouse=True\)\nasync def cleanup\(\):\n\s+# Setup\n\s+yield\n\s+# Teardown\n\s+await gum_manager\.stop_recording\(\)', fixture_replacement.strip(), content)

with open("test_backend.py", "w") as f:
    f.write(content)
