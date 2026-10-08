from importlib import import_module


def test_package_imports() -> None:
    import_module("home_ai_cluster_desktop")
