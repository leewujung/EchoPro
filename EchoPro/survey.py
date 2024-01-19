from typing import List, Union
from pathlib import Path
import pandas as pd
import numpy as np
import yaml
import copy
from .core import CONFIG_MAP, LAYER_NAME_MAP
### !!! TODO : This is a temporary import call -- this will need to be changed to 
# the correct relative structure (i.e. '.core' instead of 'EchoPro.core' at a future testing step)
import pprint
from .utils.data_structure_utils import push_nested_dict
from .utils.data_file_validation import validate_data_columns
from .computation.acoustics import to_linear , ts_length_regression
### !!! TODO : This is a temporary import call -- this will need to be changed to 
# the correct relative structure (i.e. '.utils.data_structure_utils' instead of 
# 'EchoPro.utils.data_structure_utils' at a future testing step)

class Survey:
    """
    EchoPro base class that imports and prepares parameters for
    a survey. Additionally, it includes functions for accessing
    the modules associated with the transect and Kriging variable
    calculations, CV analysis, semi-variogram algorithm, and Kriging.

    Parameters
    ----------
    init_config_path : str or pathlib.Path
        A string specifying the path to the initialization YAML file
    survey_year_config_path : str or pathlib.Path
        A string specifying the path to the survey year YAML file

    Attributes
    ----------
    meta : dict 
        Metadata variable that provides summary information concerning the
        data contained within the class object (e.g. 'self.summary').
    config : dict 
        Configuration settings and parameters that can be referenced for
        various downstream and internal functions.
    data : dict
        Various dictionaries are incorporated into the Survey class object that 
        are directly referenced for various downstream and internal functions. This
        includes attributes such as 'biology', 'acoustics', and 'spatial' that represent
        various nested biological, acoustic, and spatial/stratification datasets imported
        based on the input files defined via the configuration settings.
    
    """
    def __init__(
        self,
        init_config_path: Union[str, Path] ,
        survey_year_config_path: Union[str, Path] ,
    ):
        ### Loading the configuration settings and definitions that are used to 
        # initialize the Survey class object
        # ATTRIBUTE ADDITIONS: `config`
        self.config = self.load_configuration( Path( init_config_path ) , Path( survey_year_config_path ) )

        # Initialize data attributes ! 
        self.acoustics = copy.deepcopy(LAYER_NAME_MAP['NASC']['data_tree'])
        self.biology = copy.deepcopy(LAYER_NAME_MAP['biological']['data_tree'])
        self.spatial = copy.deepcopy(LAYER_NAME_MAP['stratification']['data_tree'])
        self.statistics = copy.deepcopy(LAYER_NAME_MAP['kriging']['data_tree'])

        ### Loading the datasets defined in the configuration files
        # EXAMPLE ATTRIBUTE ADDITIONS: `biology`, `spatial`, `acoustics`
        self.load_survey_data()

        # Define length and age distributions
        self.biometric_distributions()

        ### !!! THIS IS TEMPORARY FOR DEBUGGING / TRACKING DATA ATTRIBUTE ASSIGNMENT 
        ### A utility function that helps to map the datasets currently present
        # within Survey object via the `___.summary` property. This also initializes
        # the `meta` attribute
        # ATTRIBUTE ADDITIONS: `meta`
        ##
        # self.populate_tree()

    @staticmethod
    def load_configuration( init_config_path: Path , 
                            survey_year_config_path: Path ):
        """
        Loads the biological, NASC, and stratification
        data using parameters obtained from the configuration
        files.

        Parameters
        ----------
        init_config_path : pathlib.Path
            A string specifying the path to the initialization YAML file
        survey_year_config_path : pathlib.Path
            A string specifying the path to the survey year YAML file

        Notes
        -----
        This function parses the configuration files and incorporates them into
        the Survey class object. This initializes the `config` attribute that 
        becomes available for future reference and functions.
        """
        ### Validate configuration files
        # Retreive the module directory to begin mapping the configuration file location
        #current_directory = os.path.dirname(os.path.abspath(__file__))

        # Build the full configuration file paths and verify they exist
        config_files = [init_config_path, survey_year_config_path]
        config_existence = [init_config_path.exists(), survey_year_config_path.exists()] 

        # Error evaluation and print message (if applicable)
        if not all(config_existence):
            missing_config = [ files for files, exists in zip( config_files, config_existence ) if not exists ]
            raise FileNotFoundError(f"The following configuration files do not exist: {missing_config}")

        ### Read configuration files
        # If configuration file existence is confirmed, proceed to reading in the actual files
        ## !!! TODO: Incorporate a configuration file validator that enforces required variables and formatting
        init_config_params = yaml.safe_load(init_config_path.read_text())
        survey_year_config_params = yaml.safe_load(survey_year_config_path.read_text())        

        # Validate that initialization and survey year configuration parameters do not intersect
        config_intersect = set(init_config_params.keys()).intersection(set(survey_year_config_params.keys()))

        # Error evaluation, if applicable
        if config_intersect:
            raise RuntimeError(
                f"The initialization and survey year configuration files comprise the following intersecting variables: {config_intersect}"
            )

        ### Format dictionary that will parameterize the `config` class attribute
        # Join the initialization and survey year parameters into a single dictionary
        # Pass 'full_params' to the class instance
        return {**init_config_params, **survey_year_config_params}

    def load_survey_data( self ):
        """
        Loads the biological, NASC, and stratification
        data using parameters obtained from the configuration
        files. This will generate data attributes associated with the tags
        defined in both the configuration yml files and the reference CONFIG_MAP
        and LAYER_NAME_MAP dictionaries.
        """

        ### Check whether data files defined from the configuration file exists
        # Generate flat JSON table comprising all configuration parameter names
        flat_configuration_table = pd.json_normalize(self.config).filter(regex="filename")

        # Parse the flattened configuration table to identify data file names and paths
        parsed_filenames = flat_configuration_table.values.flatten()

        # Evaluate whether either file is missing
        data_existence = [(Path(self.config['data_root_dir']) / file).exists() for file in parsed_filenames]

        # Assign the existence status to each configuration file for error evaluation
        # Error evaluation and print message (if applicable)
        if not all(data_existence):
            missing_data = parsed_filenames[ ~ np.array( data_existence ) ]
            raise FileNotFoundError(f"The following data files do not exist: {missing_data}")
        
        ### Data validation and import
        # Iterate through known datasets and datalayers
        for dataset in [*CONFIG_MAP.keys()]:

            for datalayer in [*self.config[dataset].keys()]:

                # Define validation settings from CONFIG_MAP
                validation_settings = CONFIG_MAP[dataset][datalayer]

                # Define configuration settings w/ file + sheet names
                config_settings = self.config[dataset][datalayer]

                # Create reference index of the dictionary path
                config_map = [dataset, datalayer]

                # Define the data layer name 
                # -- Based on the lattermost portion of the file path string
                # Create list for parsing the hard-coded API dictionary
                if dataset == 'biological':
                    for region_id in [*self.config[dataset][datalayer].keys()]:

                        # Get file and sheet name
                        file_name = Path(self.config['data_root_dir']) / config_settings[region_id]['filename']
                        sheet_name = config_settings[region_id]['sheetname']
                        config_map = config_map + ['region']
                        config_map[2] = region_id

                        # Validate column names of this iterated file
                        validate_data_columns( file_name , sheet_name , config_map , validation_settings )

                        # Validate datatypes within dataset and make appropriate changes to dtypes (if necessary)
                        # -- This first enforces the correct dtype for each imported column
                        # -- This then assigns the imported data to the correct class attribute
                        self.read_validated_data( file_name , sheet_name , config_map , validation_settings )
                else:
                    file_name = Path(self.config['data_root_dir']) / config_settings['filename']
                    sheet_name = config_settings['sheetname']

                    # Validate column names of this iterated file
                    validate_data_columns( file_name , sheet_name , config_map , validation_settings )

                    # Validate datatypes within dataset and make appropriate changes to dtypes (if necessary)
                    # -- This first enforces the correct dtype for each imported column
                    # -- This then assigns the imported data to the correct class attribute
                    self.read_validated_data( file_name , sheet_name , config_map , validation_settings )

        ### Merge haul numbers and regional indices across biological variables
        # Also add strata values/indices here alongside transect numbers 
        # -- Step 1: Consolidate information linking haul-transect-stratum
        self.biology['haul_to_transect_df'] = (
            self.biology['haul_to_transect_df']
            .merge(self.spatial['strata_df'], on =['haul_num'] , how = 'outer' )
        )
        # -- Step 2: Distribute this information to the other biological variables
        # ---- Specimen 
        self.biology['specimen_df'] = (
            self.biology['specimen_df']
            .merge( self.biology['haul_to_transect_df'] , on = ['haul_num' , 'region' ] )
        )
        # ---- Length
        self.biology['length_df'] = (
            self.biology['length_df']
            .merge( self.biology['haul_to_transect_df'] , on = ['haul_num' , 'region'] )
        )
        # ---- Catch
        self.biology['catch_df'] = (
            self.biology['catch_df']
            .merge( self.biology['haul_to_transect_df'] , on = ['haul_num' , 'region'] )
        )

    def read_validated_data( self ,
                             file_name: Path ,
                             sheet_name: str ,
                             config_map: list ,
                             validation_settings: dict ):
        """
        Reads in data and validates the data type of each column/variable

        Parameters
        ----------
        file_name: Path
            The file name without the prepended file path
        sheet_name: str
            The Excel sheet name containing the target data
        config_map: list
            A list parsed from the file name that indicates how data attributes
            within `self` are organized
        validation_settings: dict
            The subset CONFIG_MAP settings that contain the target column names
        """
    
        # Based on the configuration settings, read the Excel files into memory. A format
        # exception is made for 'kriging.vario_krig_para' since it requires additional
        # data wrangling (i.e. transposing) to resemble the same dataframe format applied
        # to all other data attributes.
        # TODO : REVISIT THIS LATER
        if 'vario_krig_para' in config_map:
            # Read Excel file into memory and then transpose
            df_initial = pd.read_excel(file_name, header=None).T

            # Take the values from the first row and redfine them as the column headers
            df_initial.columns = df_initial.iloc[0]
            df_initial = df_initial.drop(0)

            # Slice only the columns that are relevant to the EchoPro module functionality
            valid_columns = list(set(validation_settings.keys()).intersection(set(df_initial.columns)))
            df_filtered = df_initial[valid_columns]

            # Ensure the order of columns in df_filtered matches df_initial
            df_filtered = df_filtered[df_initial.columns]

            # Apply data types from validation_settings to the filtered DataFrame
            df = df_filtered.apply(lambda col: col.astype(validation_settings.get(col.name, type(df_filtered.iloc[0][col.name]))))
        
        else:
            # Read Excel file into memory -- this only reads in the required columns
            df = pd.read_excel(file_name, sheet_name=sheet_name, usecols=validation_settings.keys())

            # Apply data types from validation_settings to the filtered DataFrame
            df = df.apply(lambda col: col.astype(validation_settings.get(col.name, type(col[0])))) 

        # Assign the data to their correct data attributes
        # As of now this entails:
        # -- biology --> biology
        # -- stratification --> spatial
        # -- kriging --> statistics
        # -- NASC --> acoustics
        # Step 1: Step into the data attribute 
        if LAYER_NAME_MAP[config_map[0]]['superlayer'] == []:
            attribute_name  = LAYER_NAME_MAP[config_map[0]]['name']
            internal = getattr( self , attribute_name )
        else:
            attribute_name = LAYER_NAME_MAP[config_map[0]]['superlayer'][0]
            internal = getattr( self , attribute_name )
        # ------------------------------------------------------------------------------------------------
        # Step 2: Determine whether the dataframe already exists -- this only applies to some datasets
        # such as length that comprise multiple region indices (i.e. 'US', 'CAN')
        if attribute_name in ['biology' , 'statistics' , 'spatial']:
            if attribute_name == 'biology':
                # Add US / CAN as a region index 
                df['region'] = config_map[2] 

                # Apply CAN haul number offset 
                if config_map[2] == 'CAN':
                    df['haul_num'] += self.config['CAN_haul_offset']
            
            # If kriging dataset, then step one layer deeper into dictionary
            elif config_map[0] == 'kriging':
                internal = internal['kriging']    
            
            # A single dataframe per entry is expected, so no other fancy operations are needed
            df_list = [internal[config_map[1] + '_df'] , df]
            internal[config_map[1] + '_df'] = pd.concat(df_list)

        elif attribute_name == 'acoustics':
            
            # Step forward into 'acoustics' attribute
            internal = internal['nasc']

            # Toggle through including and excluding age-1
            # -- This is required for merging the NASC dataframes together
            if config_map[1] == 'no_age1':
                df = df.rename(columns={'NASC': 'NASC_no_age1'})
            else:
                df = df.rename(columns={'NASC': 'NASC_all_ages'})
            
            column_to_add = df.columns.difference(internal['nasc_df'].columns).tolist()
            internal['nasc_df'][column_to_add] = df[column_to_add]
        
        else:
            raise ValueError('Unexpected data attribute structure. Check API settings located in the configuration YAML and core.py')
        
        # ------------------------------------------------------------------------------------------------
        # THIS IS A TEMPORARY FUNCTION
        # -- This PARASITIC_TREE function is temporarily here to continue validating data attributes are
        # -- being organized in an expected manner
        # self.PARASITIC_TREE( config_map )
        
    def biometric_distributions( self ):
        """
        Expand bin parameters into actual bins for length and age distributions
        """

        # Pull the relevant age and length bins and output a dictionary
        biometrics = {
            'length_bins_arr': np.linspace( self.config['bio_hake_len_bin'][0] ,
                                        self.config['bio_hake_len_bin'][1] ,
                                        self.config['bio_hake_len_bin'][2] ,
                                        dtype = np.int64 ) ,
            'age_bins_arr': np.linspace( self.config['bio_hake_age_bin'][0] ,
                                    self.config['bio_hake_age_bin'][1] , 
                                    self.config['bio_hake_age_bin'][2] ) ,
        }

        # Update the configuration so these variables are mappable
        self.config['biometrics'] = {
            'parameters': {
                'bio_hake_len_bin': self.config['bio_hake_len_bin'] ,
                'bio_hake_age_bin': self.config['bio_hake_age_bin']
            } ,

            # THIS LINE IS SOLELY RELATED TO THE PARASITIC TREE FUNCTIONALITY
            'dict_tree': ['biology', 'distributions', ['age_bins', 'length_bins']]
        }
        del self.config['bio_hake_len_bin'], self.config['bio_hake_age_bin']

        # Push to biology attribute 
        self.biology['distributions'] = biometrics

    def transect_analysis(self ,
                          species_id: np.float64 = 22500 ):
    #     # INPUTS
    #     # This is where the users can designate specific transect numbers,
    #     # stratum numbers, species, etc. These would be applied to the functions
    #     # below
        
    #     # Initialize new attribute
    #     self.results = {}
    #     #### TODO: THIS SHOULD BE ADDED TO THE ORIGINAL SURVEY OBJECT CREATION
    #     #### THIS IS INCLUDED HERE FOR NOW FOR TESTING PURPOSES -- ALL CAPS IS CRUISE
    #     #### CONTROL FOR "REMEMBER TO MAKE THIS CHANGE BRANDYN !!!"
                
        # Calculate sigma_bs per stratum 
        ### This will also provide dataframes for the length-binned, mean haul, and mean strata sigma_bs       
        self.strata_mean_sigma_bs( species_id )
        
        # Fill in missing strata sigma_bs values
        # self.impute_missing_sigma_bs()
    #     ### TODO: This does not necessarily need to be its own function
    #     ### It also does not need to resemble the original source code (ie for loop)
    #     missing_strata = []
    #     for stratum in self.spatial['strata_df']['stratum_num']:
    #         if stratum not in self.acoustics['sigma_df']['stratum_num']:
    #             missing_strata.append(stratum)
    #     # OR 
    #     self.impute_missing_strata()
        
        # Fill in missing sigma_bs values
        self.impute_missing_sigma_bs()
        
    #     # Fit length-weight regression required for biomass calculation
    #     self.fit_length_weight_relationship()
    #     # OUTPUT: self.statistics['length_weight_arr'] (np.ndarray)
        
    #     # Apply length-weight regression to biological data
    #     ### This will largely resemble the sigma_bs calculation
    #     ### since it also follows the "use regression to calculate value"
    #     ### workflow. So it may be more parsimonious to bundle these 
    #     ### under a shared regression function
    #     #### This also subsume the original '_get_weight_num_fraction_adult'
    #     #### INPUT: 'group' = 'all_ages', 'adult'
    #     self.strata_sex_weight_all( ... , group = ...)
    #     # OUTPUT: self.biology['weight_df'] (pd.DataFrame)
        
    #     # Synthesize all of the above steps to begin the conversion from 
    #     # integrated acoustic backscatter (ala NASC) to estimates of biological
    #     # relevance 
    #     self.nasc_to_biomass_conversion()
    #     # OUTPUT: self.biology['population'] (dict)
    #     ### Or something 'general' that encapsulates all of the calculated
    #     ### acoustic-derived biometrics
    #     # OUTPUT: self.biology['population']['areal_density_df'] (pd.DataFrame)
    #     # OUTPUT: self.biology['population']['abundance_df'] (pd.DataFrame)
    #     # OUTPUT: self.biology['population']['biomass_df'] (pd.DataFrame)
    #     ### This would stitch together "all_ages" w/ age and sex as separate columns
    #     ### resulting a melted dataframe rather than 22+ columns (with one column assigned to
    #     ### a single age-class)
        
    #     # Calculate stratified mean
    #     ### This applies the Jolly and Hampton (1990) stratified mean for transect survey designs
    #     ### that provides a weighted mean and variance estimate for specified spatial regions (or other
    #     ### similar strata definitions).
    #     self.stratified_survey_statistics()
    #     # NEW ATTRIBUTE: self.results
    #     # OUTPUT: self.results['transect_results'] (dict)
    #     ## self.results['transect_results']: {'mean': np.float64, 'cv': np.float64}
    #     ### These may be pd.DataFrame instead of np.float64 to allow for grouped calculations (e.g. 
    #     ### by sex, age, etc)
    #     ## this would provide the coefficient of variation, but the actual variance output 
    #     ## is largely arbitrary since it is simply normalized by the mean
    #     ### The name of this may be different -- it should be differentiated from the kriged 
    #     ### results -- perhaps something like "nominal_results" or something
        
    # @staticmethod
    # def kriging_analysis():
        
    #     # Organize semivariogram and kriging parameters 
    #     ... = self.statistics['kriging']['vario_krig_para_df']
    #     ### TODO: Perhaps separate 'vario.__' and 'krig.__' ?
        
    #     # Prepare kriging mesh parameterization
    #     ### This is necessary for ensuring that all required parameters
    #     ### are mapped to each node within the kriging mesh
    #     ### This would replace 'bin_dataset()' in the previous implementation
    #     self.initialize_kriging_mesh()    
        
    #     # Fit semivariogram 
    #     self.fit_semiovariogram_model()
    #     # OUTPUT: self.statistics['semivariogram'] (dict)
    #     ### Keys represent each specific model parameter such as the 
    #     ### range, sill, nugget, etc.
        
    #     # Apply semiovariogram to interpolate data over the defined kriging mesh
    #     self.kriging_interpolation()
    #     # OUTPUT: self.statistics['kriging']['modeled_biomass'] (df)
    #     ## Or perhaps this would also be appropriate under the 'biology' attribute
                
    #     # Calculate similar stratified survey analysis but this time using
    #     # kriged values
    #     self.stratified_kriging_statistics()
    #     # OUTPUT: self.results['kriging_results'] (dict)
    #     ## self.results['kriging_results']: {'mean': np.float64, 'cv': np.float64}
    #     ### These may be pd.DataFrame instead of np.float64 to allow for grouped calculations (e.g. 
    #     ### by sex, age, etc)
        
    def strata_mean_sigma_bs( self ,
                              species_id: np.float64 = 22500 ):
        
        # Reformat 'specimen_df' to match the same format as 'len_df'
        ### First make copies of each
        specimen_df_copy = self.biology['specimen_df'].copy()
        length_df_copy = self.biology['length_df'].copy()
        
        ### Iterate through 'specimen_df_copy' to grab 'length' and the number of values in that bin
        ### Indexed by 'haul_num' , 'species_id' , 'region' , 'length'
        spec_df_reframed = (
            specimen_df_copy
            .groupby(['haul_num', 'species_id', 'region', 'length'])
            .apply(lambda x: len(x['length']))
            .reset_index(name='length_count')
            )
        
        ### Concatenate the two dataframes
        all_length_df = pd.concat( [ spec_df_reframed , length_df_copy ] , join = 'inner' )
        
        ### Filter out the correct species
        all_length_df = all_length_df[ all_length_df.species_id == species_id ]
        
        # Import parameters from configuration
        ts_length_parameters = self.config['TS_length_regression_parameters']['pacific_hake']
        slope = ts_length_parameters['TS_L_slope']
        intercept = ts_length_parameters['TS_L_intercept']
        
        # Convert length values into TS
        ### ??? TODO: Not necessary for this operation, but may be useful to store for future use ?
        all_length_df[ 'TS' ] = ts_length_regression( all_length_df[ 'length' ] , slope , intercept )
        
        # Convert TS into sigma_bs
        all_length_df[ 'sigma_bs' ] = to_linear( all_length_df[ 'TS' ] )
        
        # Calculate the weighted mean sigma_bs per haul
        ### This will track both the mean sigma_bs and sample size since this will propagate as a
        ### grouped mean contained with a shared stratum
        mean_haul_sigma_bs = (
            all_length_df
            .groupby(['haul_num' , 'species_id' , 'region'])[['sigma_bs' , 'length_count']]
            .apply(lambda x: np.average( x['sigma_bs'] , weights=x['length_count']))
            .to_frame('mean_sigma_bs')
            .reset_index()
        )
                
        # Now these values can be re-merged with stratum information and averaged over strata
        mean_strata_sigma_bs = (
            mean_haul_sigma_bs
            .merge( self.spatial['strata_df'].copy() , on = 'haul_num' , how='left' )
            .groupby(['stratum_num' , 'species_id'])['mean_sigma_bs']
            .mean()
            .reset_index()
        )
        
        # Add back into object
        self.acoustics['sigma_bs'] = {
            'length_binned': all_length_df ,
            'haul_mean': mean_haul_sigma_bs ,
            'strata_mean': mean_strata_sigma_bs
        }
    
    def impute_missing_sigma_bs(self):
        
        # Collect all possible strata values
        strata_options = np.unique(self.spatial['strata_df'].copy().stratum_num)
        
        #
        strata_mean = self.acoustics['sigma_bs']['strata_mean'].copy()
        
        # impute missing strata values
        present_strata = np.unique(strata_mean['stratum_num']).astype(int)
        missing_strata = strata_options[~(np.isin(strata_options, present_strata))]
        
        if len(missing_strata) > 0:            
            sigma_bs_impute = pd.concat([strata_mean , 
                                            pd.DataFrame({'stratum_num': missing_strata ,
                                                        'species_id': np.unique( strata_mean.species_id ) ,
                                                        'mean_sigma_bs': np.nan})]).sort_values('stratum_num')        
            
            # Find strata intervals to impute over        
            for i in missing_strata:
                strata_floor = present_strata[present_strata < i]
                strata_ceil = present_strata[present_strata > i]

                new_stratum_below = np.max(strata_floor) if strata_floor.size > 0 else None
                new_stratum_above = np.min(strata_ceil) if strata_ceil.size > 0 else None      
                
                sigma_bs_indexed = sigma_bs_impute[sigma_bs_impute['stratum_num'].isin([new_stratum_below, new_stratum_above])]
                
                sigma_bs_impute.loc[sigma_bs_impute.stratum_num==i , 'mean_sigma_bs'] = sigma_bs_indexed['mean_sigma_bs'].mean()
                
            self.acoustics['sigma_bs']['strata_mean'] = sigma_bs_impute

        
   
        
    # def fit_length_weight_relationship( length_df , specimen_df ):
 
    # @staticmethod
    # def initialize_kriging_mesh():
        
    #     # Read in mesh and isobath elements
        
    #     # Standardize coordinates by longitude from isobath
    #     self.standardize_coordinates()
        
    ##############################################################################
    # EVERYTHING BELOW HERE IS PRIMARILY FOR JUST TESTING 
    # THESE FUNCTIONS ARE NOT APPLIED ELSEWHERE
    # These are all wrapped within PARASITIC_TREE(...)
    ##############################################################################
    # def PARASITIC_TREE( self ,
    #                     config_map ):
    #     # From LAYER_NAME_MAP, rename the original top layer (e.g. 'stratification' -> 'spatial')
    #     LAYER_KEY = LAYER_NAME_MAP.get(config_map[0])

    #     # From LAYER_NAME_MAP, add the 'superlayer', if defined, that adjusts the intended dictionary
    #     # nested tree structure (e.g. 'kriging/vars' -> 'statistics/kriging/vars')
    #     updated_layers = LAYER_KEY['superlayer'] + [LAYER_KEY['name']] + config_map[1:]

    #     # Determine how deep 'data_layers' is represented within the dictionary
    #     # This is required for mapping dataframes with an appropriately named
    #     # data layer name appended with '_df' (e.g. 'length' -> 'length_df')
    #     updated_name_bool = set(updated_layers).intersection(LAYER_KEY['data'])
    #     updated_layer_index = updated_layers.index(''.join(updated_name_bool))

    #     # Append '_df' to the correct data layer name. This will change the name located within the 
    #     # configuration to provide context of the datatype (in this case, as dataframe).
    #     updated_layers[updated_layer_index] = ''.join(updated_name_bool)+'_df'

    #     # Push the new nested tree data path to the config under the key: 'dict_tree'
    #     push_nested_dict(self.config, config_map + ['dict_tree'], updated_layers)
    
    # @staticmethod
    # def add_to_tree( current_layer: dict , 
    #                 data_layers: np.ndarray , 
    #                 value: list ):
    #     """
    #     Map out the data path/structure of a specific branch within a nested
    #     data tree/dictionary.
    #     """

    #     # Iterate through the next branch that represent the 
    #     # nested data tree structure of each data attribute
    #     for i, layer in enumerate(data_layers):
    #         if i < len(data_layers) - 1:
    #             if layer not in current_layer:
    #                 current_layer[layer] = {}
    #             current_layer = current_layer[layer]
    #         else:
    #             if i == len(data_layers) - 1:
    #                 current_layer.setdefault(layer, []).append(value)
    #             else:
    #                 current_layer = current_layer.setdefault(layer, [])

    # def populate_tree( self ):
    #     """
    #     Construct and populate the data structure tree and append it to the metadata attribute.
    #     """

    #     # Initialize the 'self.meta' attribute and the dictionary 'tree'.
    #     self.meta = {'tree': {}}

    #     # 'Normalize' the dictionary into a dataframe
    #     flat_configuration_table = pd.json_normalize(self.config)

    #     # Parse only the configuration values labeled 'dict_tree' -- then flatten
    #     tree_map = flat_configuration_table.filter(regex="dict_tree").values.flatten()

    #     # Iterate through all of the possible values in 'tree_map' to iteratively construct
    #     # a tree-like map of the various layers/levels/nodes contained within each of the 
    #     # class data attributes. This enables everything to be viewed in the console via the
    #     # 'summary' property function defined below.
    #     for data_layers in tree_map:
    #         self.add_to_tree(self.meta['tree'], data_layers[:-1], data_layers[-1])

    # Note : This function isn't necessary, but it is certainly helpful for debugging code along the way
    # So it may be worth removing in the future, or may be a helpful QOL utility for users. ¯\_(ツ)_/¯ 
    # @property
    # def summary( self ):
    #     """
    #     This provides a 'summary' property that can be used to quickly reference how the
    #     data attributes (and their respective nested trees) are organized within the Survey
    #     class object.
    #     """
    #     return pprint.pprint(self.meta.get('tree',{}))