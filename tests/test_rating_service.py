import pytest



from rating.rating_service import RatingService





class DummyProfile:

    def __init__(self, **kw):

        for k, v in kw.items():

            setattr(self, k, v)





class DummyRating:

    def __init__(self, **kw):

        for k, v in kw.items():

            setattr(self, k, v)





def test_primary_score_empty_profile():

    assert RatingService.calculate_primary_score(None) == 0.0





def test_primary_score_fullish():

    p = DummyProfile(

        name="Ann",

        age=25,

        city="Berlin",

        gender="female",

        bio="x" * 25,

        interests="a b c d",

        photo_urls="http://a.jpg,http://b.jpg",

        preferred_gender="any",

        preferred_age_from=20,

        preferred_age_to=40,

    )

    s = RatingService.calculate_primary_score(p)

    assert 0.5 <= s <= 1.0





def test_behavioral_default():

    r = DummyRating(total_likes=0, total_skips=0, total_matches=0, initiated_chats=0)

    s = RatingService.calculate_behavioral_score(r)

    assert 0.0 <= s <= 1.0





def test_behavioral_with_activity_hours():

    r = DummyRating(

        total_likes=10,

        total_skips=2,

        total_matches=3,

        initiated_chats=2,

        activity_by_hour='{"9": 2, "12": 3, "18": 2, "21": 1}',

    )

    s = RatingService.calculate_behavioral_score(r)

    assert 0.0 < s <= 1.0





def test_activity_time_score_empty():

    assert RatingService.activity_time_score(None) == 0.5

    assert RatingService.activity_time_score("{}") == 0.5





def test_activity_time_score_spread():

    raw = '{"8": 1, "12": 1, "18": 1, "22": 1}'

    s = RatingService.activity_time_score(raw)

    assert s > 0.5





def test_combined_bounds():

    c = RatingService.calculate_combined(0.5, 0.5, 0.1)

    assert c <= 1.0

    assert c >= 0.0





def test_photo_count_json_list():

    p = DummyProfile(photo_urls='["a","b","c"]')

    assert RatingService.photo_count(p) == 3





def test_photo_count_comma_string():

    p = DummyProfile(photo_urls="a,b")

    assert RatingService.photo_count(p) == 2


