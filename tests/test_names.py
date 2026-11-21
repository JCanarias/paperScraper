from sources.names import name_words, readable_name, same_author, surnames


def test_readable_name_drops_the_dates_and_puts_the_first_name_first():
    assert readable_name("Austen, Jane, 1775-1817") == "Jane Austen"


def test_name_words_ignore_accents_and_capitals():
    assert name_words("José Ortega y Gasset") == ["jose", "ortega", "y", "gasset"]


def test_initials_match_the_whole_first_names():
    assert same_author("W. K. C. Guthrie", "William Keith Chambers Guthrie")


def test_a_different_number_of_first_names_is_another_person():
    assert not same_author("William Guthrie", "William Keith Chambers Guthrie")
    assert not same_author("W. K. C. Guthrie", "Donna W. Guthrie")


def test_a_surname_alone_matches_anyone_with_it():
    assert same_author("Kant", "Immanuel Kant")


def test_surnames_leave_out_the_first_name_and_the_initials():
    assert surnames("Lourdes Flamarique Zaratiegui") == {"flamarique", "zaratiegui"}
    assert surnames("W. D. Ross") == {"ross"}
