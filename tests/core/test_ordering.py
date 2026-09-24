from collections import Counter

from hypothesis import given, strategies as st

from web_to_epub.core.ordering import natural_sort

names_strategy = st.lists(
    st.text(alphabet="abcABC0123456789 _-.", max_size=12), max_size=20
)


@given(names_strategy)
def test_result_is_permutation_of_input(names):
    assert Counter(natural_sort(names)) == Counter(names)


@given(names_strategy)
def test_sorting_is_idempotent(names):
    once = natural_sort(names)
    assert natural_sort(once) == once


@given(names_strategy, st.randoms(use_true_random=False))
def test_result_independent_of_input_order(names, rnd):
    shuffled = list(names)
    rnd.shuffle(shuffled)
    assert natural_sort(shuffled) == natural_sort(names)


def test_chapter_2_sorts_before_chapter_10():
    assert natural_sort(["Chapter 10", "Chapter 2"]) == ["Chapter 2", "Chapter 10"]


def test_multiple_numbers_sort_numerically():
    names = ["Chapter 10", "Chapter 1", "Chapter 9", "Chapter 100", "Chapter 2"]
    assert natural_sort(names) == [
        "Chapter 1",
        "Chapter 2",
        "Chapter 9",
        "Chapter 10",
        "Chapter 100",
    ]


def test_padded_and_unpadded_numbers_interleave_by_value():
    assert natural_sort(["ch10", "ch02", "ch1", "ch003"]) == [
        "ch1",
        "ch02",
        "ch003",
        "ch10",
    ]


def test_sorting_is_case_insensitive():
    assert natural_sort(["banana", "Apple", "cherry"]) == ["Apple", "banana", "cherry"]


def test_case_insensitive_with_numbers():
    assert natural_sort(["chapter 10", "Chapter 2"]) == ["Chapter 2", "chapter 10"]


def test_names_without_digits_sort_alphabetically():
    assert natural_sort(["Epilogue", "Prologue", "Afterword"]) == [
        "Afterword",
        "Epilogue",
        "Prologue",
    ]


def test_empty_list():
    assert natural_sort([]) == []
