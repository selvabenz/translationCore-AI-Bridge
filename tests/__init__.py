import os
# Automated tests may point at a real extracted translationCore backend. Never persist metrics or
# incidental companion state there; destructive tests explicitly use disposable project copies.
os.environ.setdefault('TC_AI_BRIDGE_TEST_MODE','1')
