"""
General analysis orchestration functions that bundle related functions and procedures
"""

import pandas as pd
import numpy as np
import warnings

from echopop.computation.acoustics import summarize_sigma_bs , nasc_to_biomass
from echopop.computation.statistics import stratified_transect_statistic

from echopop.spatial.mesh import crop_mesh , stratify_mesh
from echopop.spatial.projection import transform_geometry
from echopop.spatial.krige import kriging

from echopop.biology import (
    filter_species , 
    fit_length_weight_relationship , 
    number_proportions , 
    quantize_number_counts , 
    quantize_weights ,
    fit_length_weights , 
    weight_proportions ,
    distribute_length_age , 
    partition_transect_age ,
    sum_strata_weight , 
    calculate_aged_unaged_proportions ,
    calculate_aged_biomass , 
    calculate_unaged_biomass ,
    apply_age_bins
)

from echopop.spatial.transect import (
    edit_transect_columns , 
    transect_distance , 
    summarize_transect_strata , 
    save_transect_coordinates
)

def process_transect_data( input_dict: dict ,
                           analysis_dict: dict ,
                           settings_dict: dict ,
                           configuration_dict: dict ):
    
    # Filter out non-target species
    length_data , specimen_data , catch_data = (
        filter_species( [ input_dict[ 'biology' ][ 'length_df' ] ,
                        input_dict[ 'biology' ][ 'specimen_df' ] ,
                        input_dict[ 'biology' ][ 'catch_df' ] ] ,
                        settings_dict[ 'transect' ][ 'species_id' ] )
    )
    # ---- For cases where all samples were aged (i.e. in `specimen_data` and absent from
    # ---- `length_data`), these hauls are removed from `catch_data`
    catch_data = catch_data[ catch_data.haul_num.isin( length_data.haul_num ) ]
    
    # Save the transect coordinate information
    analysis_dict.update(
        { 'coordinates': save_transect_coordinates( input_dict[ 'acoustics' ][ 'nasc_df' ] ) }
    )

    # Calculate mean sigma_bs per individual haul, KS stratum, and INPFC stratum
    analysis_dict[ 'acoustics' ][ 'sigma_bs' ].update(
        summarize_sigma_bs( length_data , 
                            specimen_data , 
                            input_dict[ 'spatial' ] , 
                            configuration_dict ,
                            settings_dict )        
    )

    # Fit length-weight regression required for biomass calculation
    analysis_dict[ 'biology' ][ 'weight' ].update(
        fit_length_weight_relationship( 
            specimen_data , 
            input_dict[ 'biology' ][ 'distributions' ][ 'length_bins_df' ] )            
    )

    # Count the number of specimens across age and length bins
    analysis_dict[ 'biology' ][ 'distributions' ].update(
        quantize_number_counts( specimen_data , 
                                length_data , 
                                stratum = settings_dict[ 'transect' ][ 'stratum' ] )
    )

    # Calculate the number proportions
    analysis_dict[ 'biology' ][ 'proportions' ].update(
        {
            'number': number_proportions( analysis_dict[ 'biology' ][ 'distributions' ] )
        }
    )

    # Sum the weights of both aged and unaged specimens across length and weight bins
    # ---- Extract the length-weight fit
    length_weight_df = (
        analysis_dict['biology']['weight']['length_weight_regression']['weight_fitted_df']
    )
    # ---- Quantize the weights
    analysis_dict[ 'biology' ][ 'distributions' ].update(
        {
            'weight': quantize_weights( specimen_data ,
                                        length_data ,
                                        length_weight_df )
        }
    )

    # Calculate the average weights among male, female, and all fish across strata
    analysis_dict[ 'biology' ][ 'weight' ].update(
        {
            'weight_stratum_df': fit_length_weights( analysis_dict[ 'biology' ][ 'proportions' ][ 'number' ] ,
                                                     analysis_dict[ 'biology' ][ 'weight' ] )
        }
    )

    # Calculate the weight proportions
    analysis_dict[ 'biology' ][ 'proportions' ].update(
        {
            'weight': weight_proportions( specimen_data , 
                                          catch_data , 
                                          analysis_dict[ 'biology' ][ 'proportions' ][ 'number' ] ,
                                          length_weight_df ,
                                          analysis_dict[ 'biology' ][ 'distributions' ][ 'weight' ] )
        }
    )
    
    # Return the analysis dictionary
    return analysis_dict 

def acoustics_to_biology( input_dict: dict ,
                          analysis_dict: dict ,
                          configuration_dict: dict ,
                          settings_dict: dict ):
    
    # Convert NASC into number density (animals/nmi^2), biomass density (kg/nmi^2), abundance
    # (# animals), and biomass (kg) for all fish, sexed (male/female) fish, and unsexed fish
    strata_adult_proportions , nasc_to_biology = (
        nasc_to_biomass( input_dict ,
                         analysis_dict ,
                         configuration_dict ,
                         settings_dict )
    ) 

    # Distribute abundance and biomass estimates over length and age bins
    analysis_dict[ 'biology' ][ 'population' ].update(
        {
            'tables': distribute_length_age( nasc_to_biology ,                                                 
                                             analysis_dict[ 'biology' ][ 'proportions' ] ,
                                             settings_dict )
        }    
    )

    # Reapportion transect results to separate age-1 and age-2+ fish, generate age-1
    # abundance distributions for unaged fish, and generate biomass summary
    adult_transect , biomass_summary , unaged_age1_abundance = (
        partition_transect_age( nasc_to_biology , 
                                analysis_dict[ 'biology' ][ 'weight' ] ,
                                settings_dict ,
                                analysis_dict[ 'biology' ][ 'population' ] ,
                                strata_adult_proportions )
    )   

    # Append outputs to their appropriate positions within the analysis attribute
    # ---- Adult transect data
    analysis_dict[ 'acoustics' ].update( { 'adult_transect_df': adult_transect } )
    # ---- Age-1 abundances (unaged fish)
    analysis_dict[ 'biology' ][ 'population' ][ 'tables' ][ 'abundance' ].update(
        { 'unaged_age1_abundance_df': unaged_age1_abundance }
    )

    # Return the updated analysis attribute and `biomass_summary`
    return biomass_summary , analysis_dict

def stratified_summary( analysis_dict: dict ,
                        settings_dict: dict ) :
    
    # Define the and prepare the processed and georeferenced transect data
    transect_data = edit_transect_columns( analysis_dict[ 'transect' ] , settings_dict )

    # Summarize transect spatial information
    # ---- Transect distances
    transect_summary = transect_distance( transect_data )
    # ---- Counts and area coverage per stratum
    strata_summary = summarize_transect_strata( transect_summary )

    # Compute the stratified mean, variance, and coefficient of variation (CV)
    # ---- This includes the statistical (Gaussian) estimates (mean) and 95% confidence interval
    # ---- for each statistic
    replicates , stratified_results = stratified_transect_statistic( transect_data  ,
                                                                     transect_summary ,
                                                                     strata_summary ,
                                                                     settings_dict )
    
    # Update the analysis attribute with the resampled/bootstrapped replicates
    analysis_dict[ 'stratified' ].update( { 'stratified_replicates_df': replicates } )
    
    # Return the outputs
    return stratified_results , analysis_dict

def krige( input_dict: dict ,
           analysis_dict: dict ,
           settings_dict: dict ):
    
    # Extract kriging mesh data
    mesh_data = input_dict[ 'statistics' ][ 'kriging' ][ 'mesh_df' ]

    # Extract the reference grid (200 m isobath)
    isobath_data = input_dict[ 'statistics' ][ 'kriging' ][ 'isobath_200m_df' ] 

    # Define the and prepare the processed and georeferenced transect data
    transect_data = edit_transect_columns( analysis_dict[ 'transect' ] , 
                                           settings_dict )
    
    # Crop the mesh grid if the kriged data will not be extrapolated
    if not settings_dict[ 'extrapolate' ]:
        # ---- Compute the cropped mesh
        mesh_full = crop_mesh( transect_data ,
                               mesh_data ,
                               settings_dict )
        if settings_dict[ 'verbose' ]:
        # ---- Print alert 
            print( "Kriging mesh cropped to prevent extrapolation beyond the defined "
            f"""`mesh_buffer_distance` value ({settings_dict['mesh_buffer_distance']} nmi).""")
        
    else:
        # ---- Else, extract original mesh dataframe
        mesh_df = mesh_data.copy( )
        # ---- Extract longitude column name
        mesh_longitude = (
            [ col for col in mesh_df.columns if 'lon' in col.lower( ) ][ 0 ]
        )  
        # ---- Latitude
        mesh_latitude = (
            [ col for col in mesh_df.columns if 'lat' in col.lower( ) ][ 0 ]
        )
        # ---- Rename the dataframe
        mesh_full = mesh_df.copy( ).rename( columns = { f"{mesh_longitude}": 'longitude' ,
                                                        f"{mesh_latitude}": 'latitude' } ) 

    # Standardize the x- and y-coordinates, if necessary
    if settings_dict['standardize_coordinates' ]:
        # ---- Transform transect data geometry (generate standardized x- and y-coordinates)
        transect_data , d_x , d_y = (
            transform_geometry( transect_data ,
                                isobath_data  ,
                                settings_dict )
        ) 
        # ---- Transform mesh grid geometry (generate standardized x- and y-coordinates)
        mesh_full , _ , _ = (
            transform_geometry( mesh_full ,
                                isobath_data  ,
                                settings_dict ,
                                d_x , d_y )
        ) 
        if settings_dict[ 'verbose' ]:
            # ---- Print alert 
            print( """Longitude and latitude coordinates (WGS84) converted to standardized """
            """coordinates (x and y).""")
    else:
        # ---- Else, duplicate the transect longitude and latitude coordinates as 'x' and 'y'
        # -------- x
        transect_data[ 'x' ] = transect_data[ 'longitude' ]
        # -------- y
        transect_data[ 'y' ] = transect_data[ 'latitude' ]
        # ---- Duplicate the mesh grid longitude and latitude coordinates as 'x' and 'y'
        # -------- x
        mesh_full[ 'x' ] = mesh_full[ 'longitude' ]
        # -------- y
        mesh_full[ 'y' ] = mesh_full[ 'latitude' ]
    # --- Append to the analysis attribute
    analysis_dict.update( { 'kriging': { 'mesh_df': mesh_full , 'transect_df': transect_data } } )

    # Kriged results
    kriged_results = kriging( analysis_dict[ 'kriging' ][ 'transect_df' ] ,
                              analysis_dict[ 'kriging' ][ 'mesh_df' ] ,
                              settings_dict )
    
    # Stratified the kriging mesh
    kriged_results[ 'mesh_results_df' ] = stratify_mesh( input_dict ,
                                                         kriged_results[ 'mesh_results_df' ] ,
                                                         settings_dict )

    
    # Return kriged (interpolated) results
    return kriged_results , analysis_dict

def apportion_kriged_values( analysis_dict: dict ,
                             kriged_mesh: pd.DataFrame , 
                             settings_dict: dict ) -> tuple[ pd.DataFrame , 
                                                             pd.DataFrame , 
                                                             pd.DataFrame ] :
    
    # Sum the kriged weights for each stratum
    # ---- Extract stratum column name
    stratum_col = settings_dict[ 'stratum_name' ]
    # ---- Extract the biological variable (independent of area)
    biology_col = settings_dict[ 'variable' ].replace( '_density' , '' )
    # ---- Sum the kriged values for each stratum
    kriged_strata = kriged_mesh.groupby( [ stratum_col ] , observed = False )[ biology_col ].sum( )
    
    # Extract the weight proportions from the analysis object
    proportions_dict = analysis_dict[ 'transect' ][ 'biology' ][ 'proportions' ]
    # ---- Aged 
    aged_proportions = proportions_dict[ 'weight' ][ 'aged_weight_proportions_df' ].copy()
    # ---- Unaged
    unaged_proportions = proportions_dict[ 'weight' ][ 'unaged_weight_proportions_df' ].copy()
    # ---- Aged-unaged sexed weight proportions
    aged_unaged_sex_proportions = (
        proportions_dict[ 'weight' ]['aged_unaged_sex_weight_proportions_df'].copy()
        [ [ stratum_col , 'sex' , 'weight_proportion_overall_unaged' ] ]
    )
    
    # Compute the apportioned unaged kriged biological values per stratum
    # ---- Merge the unaged proportions
    unaged_sexed_apportioned = unaged_proportions.merge( aged_unaged_sex_proportions )
    # ---- Set index to stratum column
    unaged_sexed_apportioned.set_index( [ stratum_col ] , inplace = True )
    # ---- Append the stratum-aggregated values
    unaged_sexed_apportioned[ f"{biology_col}_apportioned_unaged" ] = (
        unaged_sexed_apportioned[ 'weight_proportion' ]
        * unaged_sexed_apportioned[ 'weight_proportion_overall_unaged' ] 
        * kriged_strata
    )

    # Distribute biological values over the overall proportions (i.e. relative to aged and unaged 
    # fish) for aged fish
    # ---- Set index to stratum column
    aged_proportions.set_index( [ stratum_col ] , inplace = True )
    # ---- Compute the distributed values
    aged_proportions[ f"{biology_col}_apportioned" ] = (
        aged_proportions[ 'weight_proportion_overall' ]
        * kriged_strata
    ).fillna( 0.0 )

    # Distribute the aged biological distributions over unaged length distributions to estimate
    # aged distributions
    # ---- Pivot aged data
    aged_pivot = aged_proportions.reset_index( ).pivot_table( index = [ 'sex' , 'length_bin' ] , 
                                                              columns = [ 'age_bin' ] , 
                                                              values = f"{biology_col}_apportioned" , 
                                                              aggfunc = 'sum' , 
                                                              observed = False )
    # ---- Calculate the total biomass values for each sex per length bin
    aged_length_totals = aged_pivot.sum( axis = 1 ).unstack( 'sex' )
    # ---- Pivot unaged data    
    unaged_pivot = (
        unaged_sexed_apportioned.reset_index( )
        .pivot_table( index = [ 'length_bin' ] ,
                      columns = [ 'sex' ] ,
                      values = f"{biology_col}_apportioned_unaged" ,
                      aggfunc = 'sum' ,
                      observed = False )
    )
    # ---- Calculate the new unaged biological values distributed over age    
    unaged_apportioned_values = (
        ( unaged_pivot * aged_pivot.unstack( 'sex' ) / aged_length_totals ).fillna( 0 )
    )
    
    # Imputation is required when unaged values are present but aged values are absent at shared
    # length bins! This requires an augmented implementation to address this accordingly
    # ---- Sum across all age bins (of the aged fish data) to generate totals for each row (i.e. 
    # ---- length bin)
    summed_aged_length_totals = aged_pivot.T.sum()
    # ---- Extract the indices of the summed totals that equal 0.0 for male and female fish
    # -------- Male
    male_zero_aged = np.where( summed_aged_length_totals.loc[ 'male' ] == 0.0 )[ 0 ]
    # -------- Female
    female_zero_aged = np.where( summed_aged_length_totals.loc[ 'female' ] == 0.0 )[ 0 ]
    # ---- Extract the inverse where biological totals are present
    # -------- Male
    male_nonzero_aged = np.where( summed_aged_length_totals.loc[ 'male' ] != 0.0 )[ 0 ]
    # -------- Female
    female_nonzero_aged = np.where( summed_aged_length_totals.loc[ 'female' ] != 0.0 )[ 0 ]
    # ---- Pivot the unaged data and find male and female values that are non-zero
    # -------- Male
    male_nonzero_unaged = unaged_pivot[ 'male' ].iloc[ male_zero_aged ] != 0.0
    # -------- Convert to index
    male_nonzero_unaged_idx = male_zero_aged[ male_nonzero_unaged ]
    # -------- Female
    female_nonzero_unaged = unaged_pivot[ 'female' ].iloc[ female_zero_aged ] != 0.0
    # -------- Convert to index
    female_nonzero_unaged_idx = female_zero_aged[ female_nonzero_unaged ]
    # ---- Re-pivot the unaged apportioned values (if necessary)
    if ( len( male_nonzero_unaged ) > 0 ) | ( len( female_nonzero_unaged ) ) > 0 :        
        unaged_values_pvt = (
            unaged_apportioned_values.copy()
            .unstack( ).reset_index( name = 'values' )
            .pivot_table( index = [ 'length_bin' ] ,
                        columns = [ 'sex' , 'age_bin' ] ,
                        values = 'values' ,
                        observed = False )
        )
        # ---- Find the closest indices that can be used for nearest-neighbors imputation
        if len( male_nonzero_unaged ) > 0 :
            # -------- Male
            imputed_male = (
                male_nonzero_aged[ np.argmin( 
                    np.abs( male_zero_aged[male_nonzero_unaged][ : , np.newaxis ] - male_nonzero_aged ) , 
                    axis = 1 
                ) ]
            )
            # ---- Update the values
            unaged_values_pvt.iloc[male_nonzero_unaged_idx, unaged_values_pvt.columns.get_loc('male')] = (
                unaged_pivot['male'].iloc[male_nonzero_unaged_idx].to_numpy( ) 
                * aged_pivot.loc['male'].iloc[imputed_male].T 
                / aged_length_totals['male'].iloc[imputed_male]
            ).T
        if len( female_nonzero_unaged ) > 0 :
            # -------- Female
            imputed_female = (
            female_nonzero_aged[ np.argmin( 
                    np.abs( female_zero_aged[female_nonzero_unaged][ : , np.newaxis ] - female_nonzero_aged ) , 
                    axis = 1 
                ) ]
            )
            # ---- Update the values
            unaged_values_pvt.iloc[female_nonzero_unaged_idx, unaged_values_pvt.columns.get_loc('female')] = (
                unaged_pivot['female'].iloc[female_nonzero_unaged_idx].to_numpy( ) 
                * aged_pivot.loc['female'].iloc[imputed_female].T 
                / aged_length_totals['female'].iloc[imputed_female]
            ).T
        # ---- Update the original unaged apportioned table
        unaged_apportioned_values = (
            unaged_values_pvt.unstack().reset_index(name='values')
            .pivot_table( index = [ 'length_bin' ] , 
                         columns=['age_bin' , 'sex' ] ,
                         values = 'values' ,
                         observed = False )
        )
        # ---- Alert message (if verbose = T)
        if settings_dict[ 'verbose' ]:
            # ---- Male: 
            if len( male_nonzero_unaged ) > 0:
                # ---- Get interval values
                intervals_list = [str(interval) for 
                                  interval in 
                                  male_nonzero_unaged.index[male_nonzero_unaged].values]
                # ---- Print
                print(f"""Imputed apportioned unaged male {biology_col} at length bins:\n"""
                      f"""{', '.join(intervals_list)}""" )
            # ---- Female: 
            if len( female_nonzero_unaged ) > 0:
                # ---- Get interval values
                intervals_list = [str(interval) for 
                                  interval in 
                                  female_nonzero_unaged.index[female_nonzero_unaged].values]
                # ---- Print
                print(f"""Imputed apportioned unaged female {biology_col} at length bins:\n"""
                      f"""{', '.join(intervals_list)}""" )
                
    # ---- Sum the aged and unaged estimates together
    kriged_table = (
        ( unaged_apportioned_values + aged_pivot.unstack( 'sex' ) ).unstack()
        .reset_index(name=f"{biology_col}_apportioned")
    )
    # ---- Duplicate so there is an 'all' category
    kriged_full_table = pd.concat( [ kriged_table ,
                                     kriged_table.copy( ).assign( sex = 'all' ) ] )
    # ---- Consolidate
    kriging_full_table = (
        kriged_full_table
        .groupby( [ 'length_bin' , 'age_bin' , 'sex' ] , observed = False )
        [f"{biology_col}_apportioned"]
        .sum().reset_index(name=f"{biology_col}_apportioned")
    )
    
    # Check equality between original kriged estimates and (imputed) apportioned estimates
    if kriged_table[f"{biology_col}_apportioned"].sum( ) != kriged_strata.sum( ):
        # ---- If not equal, generate warning
        warnings.warn( f"""Apportioned kriged {biology_col} does not equal the total \
        kriged mesh {biology_col}! Check for cases where values kriged values may be only present \
        in `self.results['kriging']['tables']['aged_tbl']` or \
        `self.results['kriging']['tables']['unaged_tbl']` for each sex.""")               

    # Return output
    return aged_pivot , unaged_pivot , kriged_full_table