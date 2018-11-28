
import arcpy
import logging
import math
import os
import state_utils


# ==================================================================================================
# CONFIG
# NOTE: CONVENTIONS ABOUT STRUCTURE AND NAMING UNDER INPUT DIR MUST BE FOLLOWED
# ==================================================================================================

YEAR = 2016

#OUTPUT_DIR = r'D:\projects\national_network\network_prototype\output'
OUTPUT_DIR = r'H:\Tasks\National_Network\flowable_networks\2018_05_21\output_11_19'
#OUTPUT_DIR = r'D:\Tasks\BTS_arnold\national_network\output'

MAX_DIST_FEET = 305


# ==================================================================================================

def setup_logging(output_dir):

    # log dir setup
    log_dir = os.path.join(output_dir, "logs")
    if not os.path.exists(log_dir):
        print('logs directory didn''t exist, creating it')
        os.mkdir(log_dir)

    full_path_to_log_file = os.path.join(log_dir, 
            datetime.datetime.now().strftime("step2_%Y_%m_%d") + ".log")

    # set up logging to file
    logging.basicConfig(level=logging.DEBUG,
        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M',
        filename=full_path_to_log_file,
        filemode='a')

    # set up logging to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    consoleFormat = logging.Formatter('%(levelname)-8s %(message)s')
    console.setFormatter(consoleFormat)
    logging.getLogger('').addHandler(console)

    logger = logging.getLogger('log')

    return logger
    
# ==================================================================================================
# GREAT CIRCLE DISTANCTE IN MILES
# ==================================================================================================

def great_circle_dist_miles(lon1, lat1, lon2, lat2):

    # SET DECIMAL PRECISION TO AVOID ROUNDING ERRORS
    #getcontext().prec = 10

    # CONVERT DEGREES TO RADIANS
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dy = lat2 - lat1
    dx = lon2 - lon1

    # EXECUTE HAVERSINE FORMULA
    a = math.sin(dy/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dx/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # MULTIPLY RADIAN RESULT BY RADIUS OF THE EARTH IN NAUTICAL MILES FOR RESULT
    nmi = 3440.2769 * c

    # CONVERT TO MILES
    miles = nmi * 1.15078
    return miles

# ==================================================================================================

if __name__ == "__main__":

    start_time = datetime.datetime.now()
    
    #os.system('cls')
    
    # SET UP LOGGING 
    # --------------
    logger = setup_logging(OUTPUT_DIR)
    
    arnold_states_gdb = os.path.join(OUTPUT_DIR, 'arnold_states_{}.gdb'.format(YEAR))

    
    if not os.path.exists(arnold_states_gdb):
        logger.error("couldn't find gdb: {}".format(arnold_states_gdb))
        sys.exit()
        
    arcpy.env.scratchWorkspace = os.path.join(OUTPUT_DIR, "Scratch.gdb")

    arcpy.env.workspace = arnold_states_gdb

    # CREATE THE CONNECTORS LAYER FOR STATE BORDERS
    # ---------------------------------------------
    logger.info('\tcreating connectors layer')
    if arcpy.Exists("connectors"):
        arcpy.Delete_management("connectors")
        time.sleep(1)

    sample_s7_clip_layer = arcpy.ListFeatureClasses("*_s7_clip_final")[0]

    tmp_layer = "temp_layer"

    arcpy.MakeFeatureLayer_management(sample_s7_clip_layer, tmp_layer)

    arcpy.SelectLayerByAttribute_management(
        in_layer_or_view=tmp_layer,
        selection_type='NEW_SELECTION',
        where_clause=""""YEAR_RECOR" = -99""")

    arcpy.CopyFeatures_management(tmp_layer, "connectors")

    del tmp_layer

    
    # PROCESS ALL DANGLE LAYERS
    # -------------------------

    all_dangle_layers = arcpy.ListFeatureClasses("*_state_border_dangles")
    
    master_coord_list = []

    for focus_state_fc in all_dangle_layers:

        focus_state = focus_state_fc[:2]
        
        #fips = state_utils.state_abb_to_fips(focus_state)
        
        logger.info('\tprocessing connections for {}'.format(focus_state))

        # LOAD UP THE COORDINATES FOR THE FOCUS STATE
        # -------------------------------------------
        focus_state_dngls_dict = {}
        with arcpy.da.SearchCursor(focus_state_fc, ['SHAPE@XY', 'func_class', 'nhs', 'fac_type', 'thru_lanes']) as scursor:
            for row in scursor:
                ll_tuple = (row[0], str(row[1]) + str(row[2]) + str(row[3]) + str(row[4]))
                if not ll_tuple in focus_state_dngls_dict:
                    focus_state_dngls_dict[ll_tuple] = []
                # TODO else: warn of duplicat points


        # PROCESS EACH BORDERING STATE THAT HASN'T ALREADY BEEN PROCESSED
        # ---------------------------------------------------------------

        for bordering_state in state_utils.get_bordering_states(focus_state):

            bordering_state_fc_name = "{}_state_border_dangles".format(bordering_state)

            if arcpy.Exists(bordering_state_fc_name):


                logger.info('\tconnecting from {} to {}'.format(focus_state, bordering_state))

                # LOAD THE DANGLE FOR THE BORDERING STATE. USE DICT TO PRESERVE UNIQUENESS
                # Using additional fields to help identify dangles that are the same road for
                # cases where closest road isn't the correct choice.
                bordering_state_dngls_dict = {}
                fields = ['SHAPE@XY', 'func_class', 'nhs', 'fac_type', 'thru_lanes']
                with arcpy.da.SearchCursor(bordering_state_fc_name, fields) as scursor:
                    for row in scursor:
                        ll_tuple = (row[0], str(row[1]) + str(row[2]) + str(row[3]) + str(row[4]))
                        #print(ll_tuple)
                        if not ll_tuple in bordering_state_dngls_dict:
                            bordering_state_dngls_dict[ll_tuple] = True


                # TRY TO CONNECT THEM
                # --------------------

                for focus_state_ll_tuple in focus_state_dngls_dict.keys():

                    for border_state_ll_tuple in bordering_state_dngls_dict:

                        dist_miles = great_circle_dist_miles(
                                focus_state_ll_tuple[0][0],
                                focus_state_ll_tuple[0][1],
                                border_state_ll_tuple[0][0],
                                border_state_ll_tuple[0][1]
                                )
                        # Workaround for AR-TN border
                        if (focus_state == 'AR' and bordering_state == 'TN') or (focus_state == 'TN' and bordering_state == 'AR'):
                            MAX_DIST_FEET = 610
                        
                        # Workaround for KS-MO border
                        if (focus_state == 'KS' and bordering_state == 'MO') or (focus_state == 'MO' and bordering_state == 'KS'):
                            MAX_DIST_FEET = 615
                        
                        # Workaround for MN-WI border
                        if (focus_state == 'MN' and bordering_state == 'WI') or (focus_state == 'WI' and bordering_state == 'MN'):
                            MAX_DIST_FEET = 1500
                        
                        # Workaround for NY-CT border
                        if (focus_state == 'NY' and bordering_state == 'CT') or (focus_state == 'CT' and bordering_state == 'NY'):
                            MAX_DIST_FEET = 375
                        
                        # Workaround for CO-NM border
                        if (focus_state == 'CO' and bordering_state == 'NM') or (focus_state == 'NM' and bordering_state == 'CO'):
                            MAX_DIST_FEET = 350
                            
                        if ((dist_miles * 5280) <= MAX_DIST_FEET):

                            lon_lat_dist_hit_tuple = (
                                    border_state_ll_tuple[0][0], border_state_ll_tuple[0][1], dist_miles * 5280, border_state_ll_tuple[1])

                            focus_state_dngls_dict[focus_state_ll_tuple].append(lon_lat_dist_hit_tuple)


        # WRITE OUT ALL BORDER MATCHES FOR THE CURRENT FOCUS STATE
        # --------------------------------------------------------
        MAX_DIST_FEET = 305
        edit = arcpy.da.Editor(arcpy.env.workspace)
        edit.startEditing(False, False)
        edit.startOperation()
        
        logger.info('\twriting out border matches for {}'.format(focus_state))
        
        insert_cursor = arcpy.da.InsertCursor("connectors", ["SHAPE@"])

        for focus_state_ll_tuple, match_list in focus_state_dngls_dict.items():

            if len(match_list) > 0:   # there is a match


                index_to_use = 0 # default for i item in the list
                closest_feet = 9999

                if len(match_list) > 1:
                    for i, lldist_tuple in enumerate(match_list):

                        
                        # NH-VT had issue where closest dual carriage wasn't the correct one to 
                        # connect to. Created field based on fc, nhs, fac_type, and thru_lanes to
                        # override and connect to dangle sharing these attributes. In cases where 
                        # multiple potential connection dangles have same attributes as focus, the 
                        # closest will be used. Fixed case between NH-MA where dangle 200+ ft away
                        # had matching attributes but correct dangle was only a few feet away but
                        # had different attributes. If dangle with matching attributes is over 150ft
                        # further than closest dangle, closest dangle is chosen.
                        
                        if lldist_tuple[3] == focus_state_ll_tuple[1]:
                            dist = -150 + lldist_tuple[2]
                            if dist < closest_feet:
                                closest_feet = dist
                                index_to_use = i
                            
                        if lldist_tuple[2] < closest_feet:
                            closest_feet = lldist_tuple[2]
                            index_to_use = i


                coord_list = []
                
                coord_list.append(arcpy.Point(focus_state_ll_tuple[0][0], focus_state_ll_tuple[0][1]))

                border_state_ll_tuple = match_list[index_to_use]

                coord_list.append(arcpy.Point(border_state_ll_tuple[0], border_state_ll_tuple[1]))
                
                coord_tuple = ((focus_state_ll_tuple[0][0], focus_state_ll_tuple[0][1]),
                        (border_state_ll_tuple[0], border_state_ll_tuple[1]))

                reverse_tuple = ((border_state_ll_tuple[0], border_state_ll_tuple[1]),
                        (focus_state_ll_tuple[0][0], focus_state_ll_tuple[0][1]))

                pl_geom = arcpy.Polyline(
                        arcpy.Array(coord_list),
                        arcpy.SpatialReference(4326)
                        )

                if reverse_tuple not in master_coord_list:
                    insert_cursor.insertRow([pl_geom])
                
                master_coord_list.append(coord_tuple)
                
                
        del insert_cursor
        edit.stopOperation()
        edit.stopEditing(True)

    if arcpy.Exists(os.path.join(OUTPUT_DIR, 'arnold_merged_{}.gdb'.format(YEAR))):
        arcpy.Delete_management(os.path.join(OUTPUT_DIR, 'arnold_merged_{}.gdb'.format(YEAR)))
        
    arcpy.CreateFileGDB_management(OUTPUT_DIR, 'arnold_merged_{}.gdb'.format(YEAR))
    


    # CALC LEN MILES FOR EACH "FINAL" STATE LAYER AND CONNECTORS
    # ----------------------------------------------------------

    arcpy.CalculateField_management('connectors', 'func_class', 990, 'PYTHON_9.3')

    append_layers = arcpy.ListFeatureClasses("*s7_clip_final")
    append_layers.append("connectors")

    for layer in append_layers:
        arcpy.CalculateField_management(layer, 'len_miles', '!SHAPE.LENGTH@MILES!', 'PYTHON_9.3')
    

    # MERGE ALL STATES
    # ------------------------------------

    logger.info('\tmerging all states')
    
    input_layer_list = ';'.join(append_layers)
    
    output_layer = os.path.join(
        OUTPUT_DIR,
        'arnold_merged_{}.gdb'.format(YEAR),
        "arnold_merged")

    arcpy.Merge_management(inputs=input_layer_list, output=output_layer)
    
    for state in ['VA', 'CA', 'TX']:
        if len(arcpy.ListFields(output_layer, 'FID_{}_s7_merged'.format(state))) > 0:
            arcpy.DeleteField_management(output_layer, 'FID_{}_s7_merged'.format(state))   
    
    for state in ['OK', 'WI', 'TN', 'WY', 'CA']:
        if len(arcpy.ListFields(output_layer, 'FID_{}_s7_clip'.format(state))) > 0:
            arcpy.DeleteField_management(output_layer, 'FID_{}_s7_clip'.format(state))   
    

    run_time  = datetime.datetime.now() - start_time
    logger.info('\tRun Time (H:M:S): {}'.format(run_time))

