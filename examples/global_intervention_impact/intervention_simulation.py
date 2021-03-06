import os
import pandas as pd
import numpy as np
import json

from simtools.ExperimentManager.ExperimentManagerFactory import ExperimentManagerFactory
from simtools.SetupParser import SetupParser

from dtk.utils.core.DTKConfigBuilder import DTKConfigBuilder
from simtools.ModBuilder import ModBuilder, ModFn
from simtools.Utilities.COMPSUtilities import COMPS_login

from malaria.reports.MalariaReport import add_summary_report
from simtools.Utilities.Experiments import retrieve_experiment

from sweep_functions import *

from simtools.Analysis.AnalyzeManager import AnalyzeManager
from pfpr_analyzer import PfPRAnalyzer


# variables
run_type = "intervention"  # set to "burnin" or "intervention"
burnin_id = "96e9c858-a8ce-e811-a2bd-c4346bcb1555"
asset_exp_id = "66d8416c-9fce-e811-a2bd-c4346bcb1555"

intervention_coverages = [100]
interventions = ["atsb", 'itn', 'irs', 'health_seeking']
num_runs = 1
num_coverage_bins = 5

# Serialization
print("setting up")
if run_type == "burnin":
    years = 15
    sweep_name = "MAP_II_New_Sites_Burnin"
    serialize = True
    pull_from_serialization = False
elif run_type == "intervention":
    years = 1
    sweep_name = "global_int_ex_test"
    serialize = False
    pull_from_serialization = True
else:
    raise ValueError("Unknown run type " + run_type)


# setup
location = "HPC"
SetupParser.default_block = location


cb = DTKConfigBuilder.from_defaults("MALARIA_SIM",
                                    Simulation_Duration=int(365*years),
                                    Config_Name=sweep_name,
                                    Birth_Rate_Dependence="FIXED_BIRTH_RATE",
                                    Age_Initialization_Distribution_Type= "DISTRIBUTION_COMPLEX",
                                    Num_Cores=1,

                                    # interventions
                                    Enable_Default_Reporting=0,
                                    Enable_Demographics_Risk=1,
                                    Enable_Vector_Species_Report=0,
                                    )

cb.update_params({"Disable_IP_Whitelist": 1,
                  "Enable_Property_Output": 0,
                  "Enable_Spatial_Output": 1,
                  "Spatial_Output_Channels": ["Population", "Blood_Smear_Parasite_Prevalence", 'New_Infections',
                                              'New_Clinical_Cases']
                  })

if serialize:
    cb.update_params({"Serialization_Time_Steps": [365*years]})


hates_net_prop = 0.1 # based on expert opinion from Caitlin
assign_net_ip(cb, hates_net_prop)


def add_intervention(cb, intervention, coverage, species_details) :

    if intervention == 'itn' :
        add_annual_itns(cb, year_count=1,
                        coverage=coverage,
                        initial_killing=0.3,
                        start_day=5,
                        IP=[{"NetUsage": "LovesNets"}]
          )
    elif intervention == 'irs' :
        add_irs_group(cb, coverage=coverage, decay=180,
                      start_days=[365 * start for start in range(years)])
    elif intervention == 'atsb' :
        add_atsb_by_coverage(cb, coverage=coverage,
                             killing=0.0337,
                             species_list=list(species_details.keys()))
    elif intervention == 'health_seeking' :
        add_healthseeking_by_coverage(cb, coverage=coverage,
                                      rate=0.15, drugname="AL")

    return {'intervention' : intervention,
            '%s_coverage' % intervention : coverage}


if __name__=="__main__":

    SetupParser.init()

    # collect site-specific data to pass to builder functions
    COMPS_login("https://comps.idmod.org")
    sites = pd.read_csv("site_details.csv")

    print("finding collection ids and vector details")
    site_input_dir = os.path.join("input", "sites", "all")

    with open("species_details.json") as f:
        species_details = json.loads(f.read())

    if asset_exp_id:
        print("retrieving asset experiment")
        asset_expt = retrieve_experiment(asset_exp_id)
        template_asset = asset_expt.simulations[0].tags
        cb.set_exe_collection(template_asset["exe_collection_id"])
        cb.set_dll_collection(template_asset["dll_collection_id"])
        cb.set_input_collection(template_asset["input_collection_id"])

    # Find vector proportions for each vector in our site
    site_vectors = pd.read_csv(os.path.join(site_input_dir, "vector_proportions.csv"))
    simulation_setup(cb, species_details, site_vectors)

    # reporting
    for idx, row in site_vectors.iterrows():
        add_summary_report(cb,
                           age_bins = list(range(10, 130, 10)),
                           nodes={
                               "class": "NodeSetNodeList",
                               "Node_List": [int(row["node_id"])]
                           },
                           description = row["name"])

    if pull_from_serialization:
        print("building from pickup")

        # serialization
        print("retrieving burnin")
        expt = retrieve_experiment(burnin_id)

        df = pd.DataFrame([x.tags for x in expt.simulations])
        df["outpath"] = pd.Series([sim.get_path() for sim in expt.simulations])

        df = df[df['Run_Number'] == 0]

        from_burnin_list = [
            ModFn(DTKConfigBuilder.update_params, {
                "Serialized_Population_Path": os.path.join(df["outpath"][x], "output"),
                "Serialized_Population_Filenames": [name for name in os.listdir(os.path.join(df["outpath"][x], "output")) if "state" in name],
                "Run_Number": y,
                "x_Temporary_Larval_Habitat": df["x_Temporary_Larval_Habitat"][x]})

            for x in df.index
            for y in range(num_runs)
        ]

        builder = ModBuilder.from_list([
            [burnin_fn,
             ModFn(add_intervention, intervention, coverage, species_details)]
            for burnin_fn in from_burnin_list
            for intervention in interventions
            for coverage in np.linspace(0, 1, num_coverage_bins)
        ])

    else:
        print("building burnin")
        builder = ModBuilder.from_list([[
            ModFn(DTKConfigBuilder.update_params, {
                "Run_Number": run_num,
                "x_Temporary_Larval_Habitat":10 ** hab_exp}),
        ]
            for run_num in range(10)
            for hab_exp in np.concatenate((np.arange(-3.75, -2, 0.25), np.arange(-2, 2.25, 0.1)))
        ])

    run_sim_args = {"config_builder": cb,
                    "exp_name": sweep_name,
                    "exp_builder": builder}

    em = ExperimentManagerFactory.from_cb(cb)
    em.run_simulations(**run_sim_args)

    em.wait_for_finished(verbose=True)
    assert (em.succeeded())

    analyzer = PfPRAnalyzer(expt_name=sweep_name,
                              report_names=sites["name"].tolist(),
                              sweep_variables=["Run_Number",
                                               "x_Temporary_Larval_Habitat",
                                               "intervention",
                                               "intervention_coverage"
                                               ])

    am = AnalyzeManager(em.experiment, analyzers=analyzer)
    am.analyze()
