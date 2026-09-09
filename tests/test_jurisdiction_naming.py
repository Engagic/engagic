import pytest

from scripts._jurisdiction_naming import (
    find_banana_collisions,
    make_banana,
    to_banana_slug,
    vernacular_stem,
)


@pytest.mark.parametrize(
    "name, state, expected",
    [
        ("San Mateo", "CA", "sanmateoCA"),
        ("San Mateo County", "CA", "sanmateocountyCA"),
        ("Prosper ISD", "TX", "prosperisdTX"),
        ("Prosper Independent School District", "TX", "prosperindependentschooldistrictTX"),
        ("Los Angeles Unified School District", "CA", "losangelesunifiedschooldistrictCA"),
        ("Wylie ISD (Collin County)", "TX", "wylieisdcollinTX"),
        ("Rocksprings ISD (069901)", "TX", "rockspringsisdTX"),
        ("Independent School District #272 Eden Prairie Schools", "MN", "edenprairieschoolsMN"),
        ("Independent School District 748", "MN", "isd748MN"),
        ("School District 45", "IL", "isd45IL"),
        ("Pierre School District 32-2", "SD", "pierreschooldistrict322SD"),
        ("Rice C.I.S.D.", "TX", "ricecisdTX"),
        ("La Cañada Flintridge", "ca", "lacanadaflintridgeCA"),
    ],
)
def test_banana_is_the_name_people_say(name, state, expected):
    assert make_banana(name, state) == expected


def test_vernacular_overrides_official_name():
    assert make_banana("Palo Alto Unified School District", "CA", vernacular="PAUSD") == "pausdCA"
    assert make_banana("Palo Alto Unified School District", "CA", vernacular="  ") == (
        "paloaltounifiedschooldistrictCA"
    )


def test_no_type_infix_is_manufactured():
    # The old generator turned this into prospersdTX; the district words stay.
    assert "sd" + "TX" not in make_banana("Prosper ISD", "TX").replace("isdTX", "")
    assert vernacular_stem("Fairfax County Public Schools") == "fairfaxcountypublicschools"


def test_distinct_names_do_not_collide():
    rice_cisd = make_banana("Rice CISD", "TX")
    rice_isd = make_banana("Rice ISD", "TX")
    skokie_68 = make_banana("Skokie School District 68", "IL")
    skokie_69 = make_banana("Skokie School District 69", "IL")
    assert len({rice_cisd, rice_isd, skokie_68, skokie_69}) == 4


def test_rejects_bad_state_and_empty_stem():
    with pytest.raises(ValueError):
        make_banana("San Mateo", "California")
    with pytest.raises(ValueError):
        make_banana("(069901)", "TX")


def test_collision_report_groups_duplicates():
    rows = [
        {"banana": "stlouisparkpublicschoolsMN"},
        {"banana": "stlouisparkpublicschoolsMN"},
        {"banana": "okemospublicschoolsMI"},
    ]
    assert find_banana_collisions(rows) == {"stlouisparkpublicschoolsMN": [0, 1]}


def test_slug_folds_diacritics():
    assert to_banana_slug("La Cañada") == "lacanada"
