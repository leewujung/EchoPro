from echopop.survey import Survey
import numpy as np
import pandas as pd
import geopandas as gpd
import copy
import os
from echopop.core import CONFIG_MAP, LAYER_NAME_MAP
from echopop.utils.data_file_validation import load_configuration , validate_data_columns
from echopop.computation.operations import bin_variable , bin_stats , count_variable
from echopop.utils.data_file_validation import validate_data_columns
from echopop.computation.acoustics import to_linear , ts_length_regression

obj = Survey( init_config_path='./config_files/initialization_config.yml' , survey_year_config_path='./config_files/survey_year_2019_config.yml' )
obj.transect_analysis()
obj.stratified_summary()
obj.standardize_coordinates()
obj.krige()
self = obj
kriged_results_output.columns
species_id = 22500
########### COMMON
specimen_df_copy = self.biology['specimen_df'].copy().pipe( lambda df: df.loc[ df.species_id == species_id ] )
length_df_copy = self.biology['length_df'].copy().pipe( lambda df: df.loc[ df.species_id == species_id ] )

### Pull length distribution values
length_intervals = self.biology['distributions']['length']['length_interval_arr']   
age_intervals = self.biology[ 'distributions' ][ 'age' ][ 'age_interval_arr' ]

### Calculate the sex proportions/frequencies for station 1 (length_df) across all strata        
length_grouped = (   
    length_df_copy
    .bin_variable( length_intervals , 'length' ) # appends `length_bin` column
    .assign( group = lambda x: np.where( x[ 'sex' ] == int( 1 ) , 'male' , 
                                np.where( x[ 'sex' ] == int( 2 ) , 'female' , 'unsexed' ) ) )
    # .assign( group = lambda x: np.where( x['sex'] == int(1) , 'male' , 'female' ) ) # assigns str variable for comprehension
    # .pipe( lambda df: pd.concat( [ df.loc[ df[ 'sex' ] != 3 ] , df.assign( group = 'all' ) ] ) ) # appends male-female to an 'all' dataframe
    .assign( station = 1 ) # assign station number for later functions
    )

### Calculate the sex proportions/frequencies for station 2 (specimen_df) across all strata
specimen_grouped = (
    specimen_df_copy
    .bin_variable( length_intervals , 'length' ) # appends `length_bin` column
    .assign( group = lambda x: np.where( x[ 'sex' ] == int( 1 ) , 'male' , 
                                np.where( x[ 'sex' ] == int( 2 ) , 'female' , 'unsexed' ) ) ) # assigns str variable for comprehension
    # .pipe( lambda df: pd.concat( [ df , df.assign( group = 'all' ) ] ) ) # appends male-female to an 'all' dataframe
    .dropna( subset = [ 'weight' , 'length' ] )
    .assign( station = 2 ) # assign station number for later functions
)
specimen_grouped .loc[ lambda x: x.stratum_num == 1.0 ]
### "Meld" the two datasets together to keep downstream code tidy
station_sex_length = (
    specimen_grouped # begin reformatting specimen_grouped so it resembles same structure as length_grouped
    .meld( length_grouped ) # "meld": reformats specimen_grouped and then concatenates length_grouped 
    # sum up all of the length values with respect to each length bin
    .count_variable( contrasts = [ 'group' , 'station' , 'stratum_num' , 'length_bin' ] , # grouping variables
                     variable = 'length_count' , # target value to apply a function
                     fun = 'sum' ) # function to apply
)

### Calculate total sample size ('group' == 'all') that will convert 'counts' into 'frequency/proportion'
total_n = (
    station_sex_length 
    # .loc[ station_sex_length.group.isin( [ 'all' ] ) ] # filter out to get to just 'all': this is where sex = [ 1 , 2 , 3]
    .groupby( [ 'stratum_num' ] )[ 'count' ] # group by each stratum with 'count' being the target variable
    .sum( ) # sum up counts per stratum
    .reset_index( name = 'n_total' ) # rename index
)

### Convert counts in station_sex_length into frequency/proportion
station_length_aggregate = (
    station_sex_length
    # calculate the within-sample sum and proportions (necessary for the downstream dot product calculation)
    .pipe( lambda x: x.assign( within_station_n = x.groupby( [ 'group' , 'station' , 'stratum_num' ] )[ 'count' ].transform( sum ) ,
                                within_station_p = lambda x: x[ 'count' ] / x[ 'within_station_n' ] ) )
    .replace( np.nan, 0 ) # remove erroneous NaN (divide by 0 or invalid values)
    .merge( total_n , on = 'stratum_num' ) # merge station_sex_length with total_n
    # proportion of each count indexed by each length_bin relative to the stratum total
    .assign( overall_length_p = lambda x: x[ 'count' ] / x[ 'n_total' ] ,
             overall_station_p = lambda x: x[ 'within_station_n' ] / x[ 'n_total' ] )
    .replace( np.nan, 0 ) # remove erroneous NaN (divide by 0 or invalid values)
)

station_sex_length.loc[ lambda x: x.stratum_num == 1 ].groupby( 'group' )[ 'count' ].sum()

### Calculate the sex distribution across strata
sex_proportions = (
    station_length_aggregate
    .loc[ station_length_aggregate.group.isin( ['male' , 'female'] ) ] # only parse 'male' and 'female'
    # create a pivot that will reorient data to the desired shape
    .pivot_table( index = [ 'group' , 'station' ] , 
                    columns = [ 'stratum_num' ] , 
                    values = [ 'overall_station_p' ] )
    .groupby( 'group' )
    .sum()
)



### Calculate the proportions each dataset / station contributed within each stratum
station_proportions = (
    station_length_aggregate
    .loc[ station_length_aggregate.group.isin( [ 'all' ] ) ] # only parse 'all'
    # create a pivot that will reorient data to the desired shape
    .pivot_table( index = [ 'group' , 'station' ] , 
                    columns = 'stratum_num' , 
                    values = 'overall_station_p' )
    .groupby( 'station' )
    .sum()
)

### Calculate the sex distribution within each station across strata
sex_station_proportions = (
    station_length_aggregate
    .loc[ station_length_aggregate.group.isin( ['male' , 'female'] ) ] # only parse 'male' and 'female'
    # create a pivot that will reorient data to the desired shape
    .pivot_table( index = [ 'group' , 'station' ] , 
                    columns = 'stratum_num' , 
                    values = 'overall_station_p' )
    .groupby( [ 'group' , 'station' ] )
    .sum()
)

### Merge the station and sex-station indexed proportions to calculate the combined dataset mean fractions
sex_stn_prop_merged = (
    sex_station_proportions
    .stack( )
    .reset_index( name = 'sex_stn_p')
    .merge( station_proportions
        .stack()
        .reset_index( name = 'stn_p' ) , on = [ 'stratum_num' , 'station' ] )
    .pivot_table( columns = 'stratum_num' ,
                    index = [ 'station' , 'group' ] ,
                    values = [ 'stn_p' , 'sex_stn_p' ] )    
)

### Format the length bin proportions so they resemble a similar table/matrix shape as the above metrics
# Indexed / organized by sex , station, and stratum
length_proportion_table = (
    station_length_aggregate
    .pivot_table( columns = [ 'group' , 'station' , 'stratum_num' ] , 
                    index = [ 'length_bin' ] ,
                    values = [ 'within_station_p' ] )[ 'within_station_p' ]
)

### Calculate combined station fraction means
# Station 1 
stn_1_fraction = ( sex_stn_prop_merged.loc[ 1 , ( 'stn_p' ) ]                           
                    / ( sex_stn_prop_merged.loc[ 1 , ( 'stn_p' ) ] 
                    + sex_stn_prop_merged.loc[ 2 , ( 'sex_stn_p' ) ] ) )

# Station 2
stn_2_fraction = ( sex_stn_prop_merged.loc[ 2 , ( 'sex_stn_p' ) ]                          
                    / ( stn_1_fraction
                    + sex_stn_prop_merged.loc[ 2 , ( 'sex_stn_p' ) ] ) )

### Calculate the average weight across all animals, males, and females
# Pull fitted weight values
fitted_weight = self.statistics['length_weight']['length_weight_df']

# Total
total_weighted_values = ( length_proportion_table.loc[ : , ( 'all' , 1 ) ] * station_proportions.loc[ 1 , ] +
                            length_proportion_table.loc[ : , ( 'all' , 2 ) ] * station_proportions.loc[ 2 , ] )
total_weight = fitted_weight[ 'weight_modeled' ].dot( total_weighted_values.reset_index( drop = True ) )

# Male
male_weighted_values = ( length_proportion_table.loc[ : , ( 'male' , 1 ) ] * stn_1_fraction.loc[ 'male' ] +
                            length_proportion_table.loc[ : , ( 'male' , 2 ) ] * stn_2_fraction.loc[ 'male' ] )
male_weight = fitted_weight[ 'weight_modeled' ].dot( male_weighted_values.reset_index( drop = True ) )

# Female
female_weighted_values = ( length_proportion_table.loc[ : , ( 'female' , 1 ) ] * stn_1_fraction.loc[ 'female' ] +
                            length_proportion_table.loc[ : , ( 'female' , 2 ) ] * stn_2_fraction.loc[ 'female' ] )
female_weight = fitted_weight[ 'weight_modeled' ].dot( female_weighted_values.reset_index( drop = True ) )

### Store the data frame in an accessible location
self.biology[ 'weight' ][ 'weight_strata_df' ] = pd.DataFrame( {
    'stratum_num': total_weight.index ,
    'proportion_female': sex_proportions.loc[ 'female' , : ][ 'overall_station_p' ].reset_index(drop=True) ,
    'proportion_male': sex_proportions.loc[ 'male' , : ][ 'overall_station_p' ].reset_index(drop=True) ,
    'average_weight_female': female_weight ,            
    'average_weight_male': male_weight ,
    'average_weight_total': total_weight
} )

### Reformat 'specimen_df' to match the same format as 'len_df'
# First make copies of each
specimen_df_copy = self.biology['specimen_df'].copy().pipe( lambda df: df.loc[ df.species_id == species_id ] )

# Import length bins
length_intervals = self.biology[ 'distributions' ][ 'length' ][ 'length_interval_arr' ]

### Calculate age bin proportions when explicitly excluding age-0 and age-1 fish
# Calculate age proportions across all strata and age-bins
age_proportions = (
    specimen_df_copy
    .dropna( how = 'any' )
    .count_variable( variable = 'length' ,
                        contrasts = [ 'stratum_num' , 'age' ] ,
                        fun = 'size' )
    .pipe( lambda x: x.assign( stratum_count = x.groupby( [ 'stratum_num' ] )[ 'count' ].transform( sum ) ,
                                stratum_proportion = lambda x: x[ 'count' ] / x[ 'stratum_count' ] ) )               
)

# Calculate adult proportions/contributions (in terms of summed presence) for each stratum
age_2_and_over_proportions = (
    age_proportions
    .pipe( lambda df: df
        .groupby( 'stratum_num' )
        .apply( lambda x: 1 - x.loc[ x[ 'age' ] <= 1 ][ 'count' ].sum() / x[ 'count' ].sum( ) ) ) 
    .reset_index( name = 'number_proportion' )
)

### Calculate proportional contributions of each age-bin to the summed weight of each stratum
### when explicitly excluding age-0 and age-1 fish
# Calculate the weight proportions across all strata and age-bins
age_weight_proportions = (
    specimen_df_copy
    .dropna( how = 'any' )
    .pipe( lambda x: x.assign( weight_age = x.groupby( [ 'stratum_num' , 'age' ] )[ 'weight' ].transform( sum ) ,
                            weight_stratum = x.groupby( [ 'stratum_num' ] )[ 'weight' ].transform( sum ) ) )
    .groupby( [ 'stratum_num' , 'age' ] )
    .apply( lambda x: x[ 'weight_age' ].sum( ) / x[ 'weight_stratum' ].sum ( ) )
    .reset_index( name = 'weight_stratum_proportion' )
)

# Calculate adult proportions/contributions (in terms of summed weight) for each stratum
age_2_and_over_weight_proportions = (
    age_weight_proportions
    .pipe( lambda df: df
        .groupby( 'stratum_num' )
        .apply( lambda x: 1 - x.loc[ x[ 'age' ] <= 1 ][ 'weight_stratum_proportion' ].sum()) ) 
        .reset_index( name = 'weight_proportion' ) 
)

### Now this process will be repeated but adding "sex" as an additional contrast and considering
### all age-bins
age_sex_weight_proportions = (
    specimen_df_copy
    .dropna( how = 'any' )
    .bin_variable( bin_values = length_intervals ,
                bin_variable = 'length' )
    .count_variable( contrasts = [ 'stratum_num' , 'age' , 'length_bin' , 'sex' ] ,
                    variable = 'weight' ,
                    fun = 'sum' )
    .pipe( lambda df: df.assign( total = df.groupby( [ 'stratum_num' , 'sex' ] )[ 'count' ].transform( sum ) ) )
    .groupby( [ 'stratum_num' , 'age' , 'sex' ] )
    .apply( lambda x: ( x[ 'count' ] / x[ 'total' ] ).sum() ) 
    .reset_index( name = 'weight_sex_stratum_proportion' )
    .assign( sex = lambda x: np.where( x[ 'sex' ] == 1 , 'male' , np.where( x[ 'sex' ] == 2 , 'female' , 'unsexed' ) ) )
)

### Add these dataframes to the appropriate data attribute
self.biology[ 'weight' ].update( {
    'sex_stratified': {
        'weight_proportions': age_sex_weight_proportions ,
    } ,
    'age_stratified': {
        'age_1_excluded': {
            'number_proportions': age_2_and_over_proportions ,
            'weight_proportions': age_2_and_over_weight_proportions ,
        } ,
        'age_1_included': {
            'number_proportions': age_proportions ,
            'weight_proportions': age_weight_proportions
        }
    }
} )