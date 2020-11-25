
import sys, os
if '..' not in sys.path:
    sys.path.append('..')

import numpy as np
import random as rd
import pandas as pd
import pickle
import pprint
import multiprocessing
import argparse
from lib.measures import *
from lib.experiment import Experiment, options_to_str, process_command_line, load_summary
from lib.calibrationSettings import calibration_lockdown_dates, calibration_mob_paths, calibration_states, contact_tracing_adoption
from lib.calibrationFunctions import get_calibrated_params

TO_HOURS = 24.0

if __name__ == '__main__':

    name = 'beacon-environment'
    start_date = '2021-01-01'
    end_date = '2021-01-28'
    random_repeats = 48
    full_scale = True
    verbose = True
    seed_summary_path = None
    set_initial_seeds_to = {}
    expected_daily_base_expo_per100k = 5 / 7

    smart_tracing_stats_window = (21 * TO_HOURS, 28 * TO_HOURS)

    beacon_config = dict(
        mode='all',
        # mode='visit_freq', proportion_with_beacon=0.5,
    )

    # contact tracing experiment parameters
    ps_adoption = [1.0, 0.75, 0.65, 0.5]
    spread_factors = [1.0, 2.0, 4.0, 8.0]
    theta_sim = 0.9  # only p_risk > theta are traced
    thresholds_roc = np.linspace(-0.01, 1.01, num=103, endpoint=True)

    # seed
    c = 0
    np.random.seed(c)
    rd.seed(c)

    # command line parsing
    args = process_command_line()
    country = args.country
    area = args.area
    cpu_count = args.cpu_count

    ps_adoption.append(contact_tracing_adoption[country])

    # Load calibrated parameters up to `maxBOiters` iterations of BO
    maxBOiters = 40 if area in ['BE', 'JU', 'RH'] else None
    calibrated_params = get_calibrated_params(country=country, area=area,
                                              multi_beta_calibration=False,
                                              maxiters=maxBOiters)

    # for debugging purposes
    if args.smoke_test:

        random_repeats = 16
        spread_factors = [8.0]
        full_scale = False
        ps_adoption = [1.0]
        beacon_configs = [dict(
            mode='all',
        )]
        thresholds_roc = np.array([-0.01, 0.00, 0.25, 0.5, 0.75, 0.90, 0.95, 0.97, 0.99, 0.995, 0.999, 0.9999])


    # create experiment object
    experiment_info = f'{name}-{country}-{area}'
    experiment = Experiment(
        experiment_info=experiment_info,
        start_date=start_date,
        end_date=end_date,
        random_repeats=random_repeats,
        cpu_count=cpu_count,
        full_scale=full_scale,
        verbose=verbose,
    )

    # contact tracing experiment for various options
    for fact in spread_factors:
        for p_adoption in ps_adoption:

            beta_multipliers = {
                'education': 1.0,
                'social': 1.0 * fact,
                'bus_stop': 1.0 / fact,
                'office': 1.0,
                'supermarket': 1.0,
            }

            # measures
            max_days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days

            m = [        
                # beacon measures
                # ManualTracingForAllMeasure(
                #     t_window=Interval(0.0, TO_HOURS * max_days),
                #     p_participate=1.0,
                #     p_recall=0.5),

                # beta scaling (direcly scales betas ahead of time, so upscaling is valid_
                APrioriBetaMultiplierMeasureByType(
                    beta_multiplier=beta_multipliers),       

                # standard tracing measures
                ComplianceForAllMeasure(
                    t_window=Interval(0.0, TO_HOURS * max_days),
                    p_compliance=p_adoption),
                SocialDistancingForSmartTracing(
                    t_window=Interval(0.0, TO_HOURS * max_days), 
                    p_stay_home=1.0, 
                    smart_tracing_isolation_duration=TO_HOURS * 14.0),
                SocialDistancingForSmartTracingHousehold(
                    t_window=Interval(0.0, TO_HOURS * max_days),
                    p_isolate=1.0,
                    smart_tracing_isolation_duration=TO_HOURS * 14.0),
                SocialDistancingSymptomaticAfterSmartTracing(
                    t_window=Interval(0.0, TO_HOURS * max_days),
                    p_stay_home=1.0,
                    smart_tracing_isolation_duration=TO_HOURS * 14.0),
                SocialDistancingSymptomaticAfterSmartTracingHousehold(
                    t_window=Interval(0.0, TO_HOURS * max_days),
                    p_isolate=1.0,
                    smart_tracing_isolation_duration=TO_HOURS * 14.0),
                ]

            # set testing params via update function of standard testing parameters
            def test_update(d):
                d['smart_tracing_actions'] = ['isolate', 'test']
                d['test_reporting_lag'] = 48.0
                d['tests_per_batch'] = 100000

                # isolation
                d['smart_tracing_policy_isolate'] = 'advanced-threshold'
                d['smart_tracing_isolation_threshold'] = theta_sim
                d['smart_tracing_isolated_contacts'] = 100000
                d['smart_tracing_isolation_duration'] = 14 * TO_HOURS,

                # testing
                d['smart_tracing_policy_test'] = 'advanced-threshold'
                d['smart_tracing_testing_threshold'] = theta_sim
                d['smart_tracing_tested_contacts'] = 100000

                # time span during which ROC info is computed
                d['smart_tracing_stats_window'] = smart_tracing_stats_window

                return d


            simulation_info = options_to_str(
                p_adoption=p_adoption,
                x=fact,
            )
                
            experiment.add(
                simulation_info=simulation_info,
                country=country,
                area=area,
                measure_list=m,
                beacon_config=beacon_config,
                thresholds_roc=thresholds_roc,
                test_update=test_update,
                seed_summary_path=seed_summary_path,
                set_initial_seeds_to=set_initial_seeds_to,
                set_calibrated_params_to=calibrated_params,
                full_scale=full_scale,
                lockdown_measures_active=False,
                expected_daily_base_expo_per100k=expected_daily_base_expo_per100k)
            
    print(f'{experiment_info} configuration done.')

    # execute all simulations
    experiment.run_all()

    # result = load_summary(f'beacon-environment-GER-TU/beacon-environment-GER-TU-beacon=y-p_adoption={p_adoption}.pk')
    # pprint.pprint(result.summary.tracing_stats)