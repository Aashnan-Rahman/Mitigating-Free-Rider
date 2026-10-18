import math

import pytest

import paper_v6_visuals as visuals


def responses():
    return [dict(round=20, client_id=c, trap_id=t, is_free_rider=c,
                 delta_norm=2+c+t, norm_z=-1+c+t, profile_z=3+c+t)
            for c in (0, 1) for t in (0, 1)]


def test_pair_coordinates_preserve_clients_and_average_selected_traps():
    points = visuals.paired_scores(responses())
    assert len(points) == 2
    assert points[0]['norm_z'] == -.5
    assert points[0]['profile_z'] == 3.5
    assert points[0]['diagonal'] == 4
    assert points[1]['is_free_rider'] == 1


def test_nonfinite_scores_remain_missing_not_zero_filled():
    rows = responses()
    rows[0]['norm_z'] = 'nan'
    points = visuals.paired_scores(rows)
    assert points[0]['norm_z'] is None and points[0]['diagonal'] is None
    summaries = visuals.summarize(points, dict(dataset='mnist'))
    summary = next(r for r in summaries if r['is_free_rider'] == 0 and r['field'] == 'norm_z')
    assert summary['clients'] == 1 and summary['finite'] == 0 and summary['undefined'] == 1
    assert summary['mean'] is None


def test_audit_or_incomplete_pair_does_not_create_full_cycle_point():
    assert len(visuals.paired_scores(responses()[:-1])) == 1


def test_duplicate_pair_and_inconsistent_labels_are_rejected():
    rows = responses()
    with pytest.raises(ValueError, match='Duplicate'):
        visuals.paired_scores(rows + rows[:1])
    rows[0]['is_free_rider'] = 1
    with pytest.raises(ValueError, match='Inconsistent'):
        visuals.paired_scores(rows)


def test_evaluation_colors_cannot_change_score_coordinates():
    rows = responses()
    original = visuals.paired_scores(rows)
    for row in rows:
        row['is_free_rider'] = 1 - row['is_free_rider']
    flipped = visuals.paired_scores(rows)
    for before, after in zip(original, flipped):
        assert all(before[field] == after[field] for field in visuals.FIELDS)


def test_display_transform_is_invertible_and_does_not_clip_extremes():
    for value in (-1e6, -2, 0, 2, 1e6):
        assert math.sinh(math.asinh(value)) == pytest.approx(value)


def test_model_payload_uses_actual_float_buffer_counts(tmp_path):
    visuals.model_resources(tmp_path)
    rows = visuals.io.read_csv(tmp_path/'generated/model_payload.csv')
    assert [int(r['profile_tensors']) for r in rows] == [8, 22]
    assert [int(r['float_coordinates']) for r in rows] == [206922, 621258]
    assert int(rows[1]['parameters']) == 620810
    assert float(rows[1]['two_trap_mib']) == pytest.approx(2*4*621258/2**20)


def test_main_text_moves_recall_to_appendix_and_retains_visual_limitations():
    from build_paper_v6_full_study import OUT
    source = (OUT/'paper_v6.tex').read_text(encoding='utf-8')
    assert source.index(r'\appendices') < source.index(r'\input{generated/recall_figure.tex}')
    assert r'\section{Complexity and Lightweight Design}' in source
    assert 'scatter_mnist_40.tex' in source and 'scatter_cifar10_40.tex' in source
