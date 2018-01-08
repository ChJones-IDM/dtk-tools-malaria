import random
from dtk.interventions.triggered_campaign_delay_event import triggered_campaign_delay_event


positive_broadcast = {
        "class": "BroadcastEvent",
        "Broadcast_Event": "TestedPositive"
        }


def add_diagnostic_survey(cb, coverage=1, repetitions=1, tsteps_btwn=365, target='Everyone', start_day=0,
                          diagnostic_type='NewDetectionTech', diagnostic_threshold=40, event_name="Diagnostic Survey",
                          node_cfg={"class": "NodeSetAll"}, positive_diagnosis_configs=[],
                          received_test_event='Received_Test', IP_restrictions=[], NP_restrictions=[],
                          pos_diag_IP_restrictions=[], trigger_condition_list=[], listening_duration=-1, triggered_campaign_delay=0 ):
    """
    Function to add recurring prevalence surveys with configurable diagnostic
    When using "trigger_condition_list", the diagnostic is triggered by the words listed

    :param cb: Configuration builder holding the interventions
    :param repetitions: Number of repetitions
    :param tsteps_btwn:  Timesteps between repetitions
    :param target: Target demographic. Default is 'Everyone'
    :param start_day: Start day for the outbreak
    :param coverage: probability an individual receives the diagnostic
    :param diagnostic_type: 
    :param diagnostic_threshold: sensitivity of diagnostic in parasites per uL
    :param nodes: nodes to target.
    # All nodes: {"class": "NodeSetAll"}.
    # Subset of nodes: {"class": "NodeSetNodeList", "Node_List": list_of_nodeIDs}
    :param positive_diagnosis_configs: list of events to happen to individual who receive a positive result from test
    :param received_test_event: string for individuals to broadcast upon receiving diagnostic
    :param IP_restrictions: list of IndividualProperty restrictions to restrict who takes action upon positive diagnosis
    :param NP_restrictions: node property restrictions
    :param trigger_condition_list: list of strings that will trigger a diagnostic survey.
    :param listening_duration: for diagnostics that are listening for trigger_condition_list, how long after start day to stop listening for the event
    :param triggered_campaign_delay: delay of running the campaign/intervention after receiving a trigger from the trigger_condition_list
    :return: nothing
    """

    intervention_cfg = {
                        "Diagnostic_Type": diagnostic_type, 
                        "Detection_Threshold": diagnostic_threshold, 
                        "class": "MalariaDiagnostic"                                          
                        }

    if not positive_diagnosis_configs :
        intervention_cfg["Event_Or_Config"] = "Event"
        intervention_cfg["Positive_Diagnosis_Event"] = "TestedPositive"    
    else :
        intervention_cfg["Event_Or_Config"] = "Config"
        intervention_cfg["Positive_Diagnosis_Config"] = { 
            "Intervention_List" : positive_diagnosis_configs + [positive_broadcast] ,
            "class" : "MultiInterventionDistributor" 
            }
        if pos_diag_IP_restrictions :
            intervention_cfg["Positive_Diagnosis_Config"]["Property_Restrictions_Within_Node"] = pos_diag_IP_restrictions

    if trigger_condition_list:
        if repetitions > 1 or triggered_campaign_delay > 0:
            event_to_send_out = random.randrange(100000)
            for x in range(repetitions): # there is at least one repetition, so it always makes at least 1 triggered event broadcast.
                # create a trigger for each of the delays.
                triggered_campaign_delay_event(cb, start_day, node_cfg,
                                                                             triggered_campaign_delay + x * tsteps_btwn,
                                                                             trigger_condition_list,
                                                                             listening_duration, event_to_send_out)
                trigger_condition_list = [event_to_send_out]

        survey_event = {"class": "CampaignEvent",
                        "Start_Day": start_day,
                        "Event_Name": event_name,
                        "Nodeset_Config": node_cfg,
                        "Event_Coordinator_Config": {
                            "class": "StandardInterventionDistributionEventCoordinator",
                            "Number_Distributions": -1,
                            "Intervention_Config":
                                {
                                    "class": "NodeLevelHealthTriggeredIV",
                                    "Trigger_Condition_List": trigger_condition_list,
                                    "Target_Residents_Only": 1,
                                    "Duration": listening_duration,
                                    "Demographic_Coverage": coverage,
                                    "Target_Demographic": target,
                                    "Property_Restrictions_Within_Node": IP_restrictions,
                                    "Node_Property_Restrictions": NP_restrictions,
                                    "Actual_IndividualIntervention_Config":
                                        {
                                            "class": "MultiInterventionDistributor",
                                            "Intervention_List": [
                                                {
                                                 "class": "BroadcastEvent",
                                                 "Broadcast_Event": received_test_event
                                                },
                                                intervention_cfg
                                            ]
                                        }
                                 },
                            }
                        }

        if isinstance(target, dict) and all([k in target.keys() for k in ['agemin', 'agemax']]):
            survey_event["Event_Coordinator_Config"]['Intervention_Config'].update({
                "Target_Demographic": "ExplicitAgeRanges",
                "Target_Age_Min": target['agemin'],
                "Target_Age_Max": target['agemax']})

        cb.add_event(survey_event)

    else:
        survey_event = { "class" : "CampaignEvent",
                         "Start_Day": start_day,
                         "Event_Name" : event_name,
                         "Event_Coordinator_Config": {
                             "class": "StandardInterventionDistributionEventCoordinator",
                             "Node_Property_Restrictions": NP_restrictions,
                             "Property_Restrictions_Within_Node": IP_restrictions,
                             "Number_Distributions": -1,
                             "Number_Repetitions": repetitions,
                             "Timesteps_Between_Repetitions": tsteps_btwn,
                             "Demographic_Coverage": coverage,
                             "Target_Demographic": target,
                             "Intervention_Config": {
                                 "Intervention_List" : [
                                     { "class": "BroadcastEvent",
                                       "Broadcast_Event": received_test_event },
                                                           intervention_cfg ] ,
                                 "class" : "MultiInterventionDistributor" }
                             },
                         "Nodeset_Config": node_cfg
                         }

        if isinstance(target, dict) and all([k in target.keys() for k in ['agemin','agemax']]) :
            survey_event["Event_Coordinator_Config"].update({
                    "Target_Demographic": "ExplicitAgeRanges",
                    "Target_Age_Min": target['agemin'],
                    "Target_Age_Max": target['agemax'] })

        cb.add_event(survey_event)

    return
