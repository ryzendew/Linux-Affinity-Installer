"""OpenCL is turned off only on the Wine builds where it deadlocks Affinity."""
from affinity_manager.commands import affinity_env, wine_build_version


def test_build_versions_are_read_from_the_name():
    assert wine_build_version("ElementalWarrior-wine-11.19") == (11, 19)
    assert wine_build_version("ElementalWarrior-wine-11.12-v4") == (11, 12)
    assert wine_build_version("system wine (wined3d fallback -- not comparable)") is None


def test_opencl_is_off_from_11_11_to_11_18():
    for build in ("ElementalWarrior-wine-11.11", "ElementalWarrior-wine-11.16", "ElementalWarrior-wine-11.18"):
        assert affinity_env(build) == {"WINEDLLOVERRIDES": "opencl=d"}


def test_opencl_is_left_alone_from_11_19_and_before_11_11():
    assert affinity_env("ElementalWarrior-wine-11.19") == {}
    assert affinity_env("ElementalWarrior-wine-11.0") == {}


def test_an_unknown_build_keeps_it_off():
    assert affinity_env("system wine (wined3d fallback -- not comparable)") == {"WINEDLLOVERRIDES": "opencl=d"}
