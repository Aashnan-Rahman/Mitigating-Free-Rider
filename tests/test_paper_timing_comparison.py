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


def test_completed_full_runs_replace_projections_without_pooling_old_pilots(tmp_path):
    import csv
    import json
    from paper_timing_comparison import build,csv_text
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
    output=tmp_path/'paper'
    result=build(tmp_path,output)
    std=[r for r in result['totals'] if r['method']=='std_100']
    assert len(std)==2 and all(r['evidence']=='measured' and r['rounds']==100 for r in std)
    assert all(r['mean_s']==57.5 and r['summed_s']==5750 for r in std)
    assert 'projection' not in (output/'generated/timing/provenance.json').read_text()
    assert 'STD 1--100' in (output/'generated/timing_segments_figure.tex').read_text()
    assert len((output/'generated/timing/std_rounds_mnist.dat').read_text().splitlines())==101
