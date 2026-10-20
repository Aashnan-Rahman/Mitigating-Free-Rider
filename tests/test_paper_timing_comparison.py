import pytest

from paper_timing_comparison import phase_summary, validate_rounds


def test_phase_costs_are_whole_round_sums_divided_by_full_horizon():
    rows=[dict(round=1,phase='warmup',round_time_seconds=10),
          dict(round=2,phase='double_probe',round_time_seconds=20),
          dict(round=3,phase='confirmation',round_time_seconds=30),
          dict(round=4,phase='single_audit',round_time_seconds=40),
          dict(round=5,phase='idle',round_time_seconds=50)]
    result=phase_summary(rows,{3})
    assert [r['rounds'] for r in result]==[1,1,1,1,1]
    assert [r['amortized_s'] for r in result]==[2,4,6,8,10]
    assert sum(r['amortized_s'] for r in result)==30
    assert result[2]['mean_within_phase_s']==30


def test_absent_phase_has_no_fabricated_within_phase_mean():
    result=phase_summary([dict(round=1,phase='warmup',round_time_seconds=10)],set())
    assert result[1]['rounds']==0 and result[1]['mean_within_phase_s'] is None
    assert result[1]['amortized_s']==0


def test_round_validation_rejects_partial_and_duplicate_sequences():
    validate_rounds([dict(round=1),dict(round=2)],2)
    for rows in ([dict(round=1)], [dict(round=1),dict(round=1)], [dict(round=2),dict(round=1)]):
        with pytest.raises(ValueError):
            validate_rounds(rows,2)


def test_timing_report_skips_missing_evidence_without_inventing_measurements(tmp_path):
    from paper_timing_comparison import build
    out=tmp_path/'paper'
    assert build(tmp_path,out) is None
    assert not (out/'generated/timing/totals.csv').exists()
    assert 'unavailable' in (out/'generated/timing_comparison.tex').read_text()


def test_negative_or_nonfinite_timings_are_rejected():
    for value in (-1,float('inf'),float('nan')):
        with pytest.raises(ValueError):
            phase_summary([dict(round=1,phase='warmup',round_time_seconds=value)],set())


@pytest.fixture
def full_timing_evidence(tmp_path):
    import json
    from paper_timing_comparison import csv_text
    def write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))
    for dataset in ('mnist','cifar10'):
        std=tmp_path/f'results/std_dagmm_100_seed42_fr40/std_dagmm_{dataset}_noniid_FR3_seed42'
        ours=tmp_path/f'results/v15_4_{dataset}_seed42_fr40/v15_4_{dataset}_noniid_FR3_seed42'
        config=dict(dataset=dataset,distribution='noniid',seed=42,num_clients=100,num_rounds=100,
            attack_type='FR3',free_rider_pct=.4,local_epochs=3,batch_size=32,learning_rate=.01,momentum=.9,dirichlet_alpha=.5)
        write(std/'summary.json',dict(state='completed',completed_rounds=100,
            protocol=dict(config=config,source_sha256={})))
        write(std/'status.json',dict(state='completed'))
        write(std/'protocol.json',{})
        write(ours/'latest_results.json',dict(completed=True,latest_round=100))
        write(ours/'run_config.json',config)
        native=[]
        for r in range(1,101):
            row=dict(round=r,active_clients=100,permanent_removals=0,honest_training_seconds=r,
                fabrication_seconds=1,aggregation_seconds=1,evaluation_seconds=1,
                preparation_seconds=1,fit_seconds=1,inference_seconds=1,decision_seconds=1,
                round_compute_seconds=r+7,detector_seconds=4)
            native.append(row)
        (std/'round_timings.csv').write_text(csv_text(native))
        (ours/'global_metrics.csv').write_text(csv_text([dict(round=r,phase='idle',
            round_time_seconds=2,num_active_clients=100,new_removals=0) for r in range(1,101)]))
        (ours/'cycle_decisions.csv').write_text('round\n20\n')
        # Malformed old pilot deliberately must never be opened/pooled.
        write(tmp_path/f'analysis/std_dagmm_{dataset}_native_seed42_fr40_FR3_noniid/summary.json',{})
    return tmp_path


def test_completed_full_runs_are_the_only_comparison_horizon(full_timing_evidence):
    from paper_timing_comparison import build
    tmp_path = full_timing_evidence
    output=tmp_path/'paper'
    result=build(tmp_path,output)
    std=[r for r in result['totals'] if r['method']=='std_100']
    assert len(std)==2 and all(r['evidence']=='measured' and r['rounds']==100 for r in std)
    assert all(r['mean_s']==57.5 and r['summed_s']==5750 for r in std)
    assert len(result['totals']) == 4
    assert {r['method'] for r in result['totals']} == {'ours_100', 'std_100'}
    assert all(r['rounds'] == 100 for r in result['totals'])
    assert 'projection' not in (output/'generated/timing/provenance.json').read_text()
    tables = (output/'generated/timing_tables.tex').read_text()
    segments = (output/'generated/timing_segments_figure.tex').read_text()
    assert '100 measured rounds' in segments
    assert 'first10' not in (output/'generated/timing/totals.csv').read_text()
    assert all(old not in tables + segments for old in ('1--10,', 'Projected', 'warm-up & 10'))
    assert len((output/'generated/timing/std_rounds_mnist.dat').read_text().splitlines())==101


def test_phase_figure_separates_event_duration_from_weighted_contribution(full_timing_evidence):
    from paper_timing_comparison import build
    output = full_timing_evidence / 'paper'
    build(full_timing_evidence, output)
    text = (output/'generated/timing_phases_figure.tex').read_text()
    assert 'group size=2 by 2' in text
    assert 'ybar stacked' not in text
    assert text.count(r'\nextgroupplot') == 4
    assert 'cost of one category round' in text and 'contribution to' in text
    assert 'n=99' in text and 'n=1' in text and 'n=0' in text
    assert 'nodes near coords' in text
    assert 'NOT detector-only time' in text
    # No fabricated mean-of-empty-category bar; zeros remain valid contributions.
    assert text.count(r'\addplot') == 14


def test_old_pilots_alone_cannot_supply_paper_timing(tmp_path):
    import json
    from paper_timing_comparison import build
    for dataset in ('mnist', 'cifar10'):
        folder = tmp_path/f'analysis/std_dagmm_{dataset}_native_seed42_fr40_FR3_noniid'
        folder.mkdir(parents=True)
        (folder/'summary.json').write_text(json.dumps(dict(completed_rounds=10)))
    out = tmp_path/'paper'
    assert build(tmp_path, out) is None
    assert not (out/'generated/timing/totals.csv').exists()
    assert '100-round timing evidence unavailable' in (out/'generated/timing_comparison.tex').read_text()


@pytest.mark.parametrize('problem', ['summary_horizon', 'summary_state', 'missing_round'])
def test_incomplete_full_evidence_is_rejected_not_replaced_by_pilots(full_timing_evidence, problem):
    import json
    from paper_timing_comparison import build
    native = full_timing_evidence/'results/std_dagmm_100_seed42_fr40/std_dagmm_mnist_noniid_FR3_seed42'
    if problem == 'missing_round':
        path = native/'round_timings.csv'
        path.write_text('\n'.join(path.read_text().splitlines()[:-1]) + '\n')
    else:
        path = native/'summary.json'
        value = json.loads(path.read_text())
        value['completed_rounds' if problem == 'summary_horizon' else 'state'] = 10 if problem == 'summary_horizon' else 'running'
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        build(full_timing_evidence, full_timing_evidence/'paper')
