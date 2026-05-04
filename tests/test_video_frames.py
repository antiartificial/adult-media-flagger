from adult_media_flagger.video_frames import evenly_spaced_timestamps


def test_evenly_spaced_timestamps():
    values = evenly_spaced_timestamps(100.0, 5)
    assert len(values) == 5
    assert values[0] > 0
    assert values[-1] < 100
    assert values == sorted(values)


def test_evenly_spaced_single_timestamp():
    assert evenly_spaced_timestamps(10.0, 1) == [5.0]

