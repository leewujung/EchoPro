import re
from typing import Any, Dict, List, Literal, Optional, TypedDict, Union, get_args

import numpy as np
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator, RootModel

from .validate import posfloat, posint, realcircle, realposfloat


####################################################################################################
# UTILITY FUNCTGIONS
# --------------------------------------------------------------------------------------------------
def describe_type(expected_type: Any) -> str:
    """
    Convert a type hint into a human-readable string.
    """

    if hasattr(expected_type, "__failstate__"):
        return expected_type.__failstate__

    if hasattr(expected_type, "__origin__"):
        origin = expected_type.__origin__

        if origin is Literal:
            return f"one of {expected_type.__args__}"

        if origin is Union:
            args = expected_type.__args__
            descriptions = [describe_type(arg) for arg in args if arg is not type(None)]
            if not descriptions:
                return "any value"
            return " or ".join(descriptions)

        if origin is np.ndarray:
            return "numpy.ndarray of floats"

        if origin is list:
            item_type = expected_type.__args__[0]
            return f"list of '{describe_type(item_type)}'"

    if isinstance(expected_type, type):
        return f"'{expected_type.__name__}'"

    # return str(expected_type)
    return f"'{expected_type}'"


def validate_type(value: Any, expected_type: Any) -> bool:
    """
    Validate if the value matches the expected type.
    """

    # Handle numpy.ndarray
    if hasattr(expected_type, "__origin__") and expected_type.__origin__ is np.ndarray:
        return (
            isinstance(value, np.ndarray)
            and np.issubdtype(value.dtype, np.number)
            # and value.dtype == np.float64
        )

    # Handle base `type` case
    if isinstance(expected_type, type):
        # ---- Handle `posint`
        if expected_type in [posint, posfloat, realposfloat, realcircle]:
            try:
                expected_type(value)
                return True
            except (TypeError, ValueError):
                return False
        else:
            return isinstance(value, expected_type)

    # Handle Union
    if hasattr(expected_type, "__origin__") and expected_type.__origin__ is Union:
        return any(validate_type(value, arg) for arg in expected_type.__args__)

    # Handle Literal
    if hasattr(expected_type, "__origin__") and expected_type.__origin__ is Literal:
        # ---- Get allowed values
        allowed_values = get_args(expected_type)
        if isinstance(value, np.ndarray):
            allowed_values_array = np.array(list(allowed_values), dtype=object)
            value_array = np.array(value, dtype=object)
            return np.array_equal(np.sort(value_array), np.sort(allowed_values_array))
        return value in allowed_values

    # Handle List
    if hasattr(expected_type, "__origin__") and expected_type.__origin__ is list:
        if not isinstance(value, list):
            return False
        item_type = expected_type.__args__[0]
        return all(validate_type(item, item_type) for item in value)

    return False


def validate_typed_dict(data: Dict[str, Any], expected_types: Dict[str, Any]) -> None:
    """
    Validate a dictionary against expected types.
    """
    for key, expected_type in expected_types.items():
        if key in data:
            if not validate_type(data[key], expected_type):
                expected_description = describe_type(expected_type)
                actual_description = type(data[key]).__name__
                if hasattr(expected_type, "__failstate__"):
                    raise TypeError(
                        f"Value for '{key}' ({data[key]}, type: '{actual_description}') "
                        f"{expected_description}."
                    )
                else:
                    raise TypeError(
                        f"Value for '{key}' ({data[key]}, type: '{actual_description}') does not "
                        f"match expected type {expected_description}."
                    )


####################################################################################################
# PYDANTIC VALIDATORS
# --------------------------------------------------------------------------------------------------


class FileSettings(BaseModel):
    """
    Parameter file settings
    """

    directory: str
    sheetname: str


class StratifiedSurveyMeanParameters(BaseModel, arbitrary_types_allowed=True):
    """
    Stratified sampling parameters
    """

    strata_transect_proportion: posfloat
    num_replicates: posint
    mesh_transects_per_latitude: posint

    @field_validator("num_replicates", "mesh_transects_per_latitude", mode="before")
    def validate_posint(cls, v):
        return posint(v)

    @field_validator("strata_transect_proportion", mode="before")
    def validate_posfloat(cls, v):
        return posfloat(v)


class KrigingParameters(BaseModel, arbitrary_types_allowed=True):
    """
    Kriging model parameters
    """

    A0: posfloat
    longitude_reference: float
    longitude_offset: float
    latitude_offset: float

    @field_validator("A0", mode="before")
    def validate_posfloat(cls, v):
        return posfloat(v)


class HaulTransectMap(BaseModel, arbitrary_types_allowed=True):
    """
    Haul-to-transect key mapping generation parameters
    """

    save_file_template: str
    country_code: List[str]
    file_settings: Dict[str, FileSettings]

    @model_validator(mode="before")
    def validate_country_files(cls, values):
        # ---- Get the country code list
        country_codes = values.get("country_code", [])
        # ---- Get file settings keys
        file_settings_keys = list(values.get("file_settings", {}).keys())
        # ---- Keys within `file_settings` must match those defined in `country_code`
        if not set(file_settings_keys) == set(country_codes):
            # ---- Raise error
            raise ValueError(
                f"File settings keys {file_settings_keys} must match those defined in "
                f"'country_code' ({country_codes})."
            )
        # ---- Return values
        return values

    @field_validator("save_file_template", mode="after")
    def validate_save_file_template(cls, v):
        # ---- Find all strings contained within curly braces
        template_ids = re.findall(r"{(.*?)}", v)
        # ---- Evaluate valid id's
        if not set(template_ids).issubset(set(["YEAR", "COUNTRY"])):
            # ---- Get the unknown IDs
            unknown_ids = set(template_ids) - set(["YEAR", "COUNTRY"])
            # ---- Raise Error
            raise ValueError(
                f"Haul-to-transect mapping save file template ({v}) contains invalid identifiers "
                f"({list(unknown_ids)}). Valid identifiers within the filename template (bounded "
                f"by curly braces) include: ['YEAR', 'COUNTRY']."
            )
        # ---- Return values
        return v


class PatternParts(BaseModel):
    """
    String pattern parts
    """

    pattern: str
    label: str


class TransectRegionMap(BaseModel, arbitrary_types_allowed=True):
    """
    Transect-to-region mapping parameters
    """

    save_file_template: str
    save_file_directory: str
    save_file_sheetname: str
    pattern: str
    parts: Dict[str, List[PatternParts]]

    @model_validator(mode="before")
    def validate_pattern_parts(cls, values):
        # ---- Get the country code list
        pattern_codes = values.get("pattern", "")
        # ---- Extract the codes
        codes = re.findall(r"{(.*?)}", pattern_codes)
        # ---- Get file settings keys
        parts_keys = list(values.get("parts", {}).keys())
        # ---- Keys within `file_settings` must match those defined in `country_code`
        if not set(parts_keys) == set(codes):
            # ---- Raise error
            raise ValueError(
                f"Defined pattern dictionary keys {parts_keys} must match those defined in "
                f"'pattern' ({codes})."
            )
        # ---- Return values
        return values

    @field_validator("save_file_template", mode="after")
    def validate_save_file_template(cls, v):
        # ---- Find all strings contained within curly braces
        template_ids = re.findall(r"{(.*?)}", v)
        # ---- Evaluate valid id's
        if not set(template_ids).issubset(set(["YEAR", "COUNTRY", "GROUP"])):
            # ---- Get the unknown IDs
            unknown_ids = set(template_ids) - set(["YEAR", "COUNTRY", "GROUP"])
            # ---- Raise Error
            raise ValueError(
                f"Transect-to-region mapping save file template ({v}) contains invalid identifiers "
                f"({list(unknown_ids)}). Valid identifiers within the filename template (bounded "
                f"by curly braces) include: ['YEAR', 'COUNTRY', 'GROUP']."
            )
        # ---- Return value
        return v

    @field_validator("pattern", mode="after")
    def validate_pattern(cls, v):
        # ---- Find all strings contained within curly braces
        template_ids = re.findall(r"{(.*?)}", v)
        # ---- Evaluate valid id's
        if not set(template_ids).issubset(set(["REGION_CLASS", "HAUL_NUM", "COUNTRY"])):
            # ---- Get the unknown IDs
            unknown_ids = set(template_ids) - set(["REGION_CLASS", "HAUL_NUM", "COUNTRY"])
            # ---- Raise Error
            raise ValueError(
                f"Transect-to-region mapping save file template ({v}) contains invalid identifiers "
                f"({list(unknown_ids)}). Valid identifiers within the filename template (bounded "
                f"by curly braces) include: ['REGION_CLASS', 'HAUL_NUM', 'COUNTRY']."
            )
            # ---- Return value
        return v


class TSLRegressionParameters(BaseModel):
    """
    Target strength - length regression parameters
    """

    number_code: int
    TS_L_slope: float = Field(allow_inf_nan=False)
    TS_L_intercept: float = Field(allow_inf_nan=False)
    length_units: str


class Geospatial(BaseModel):
    """
    Geospatial parameters
    """

    init: str

    @field_validator("init", mode="before")
    def validate_init(cls, v):
        # ---- Convert to a string if read in as an integer
        if isinstance(v, (int, float)):
            v = str(v)
        # ---- Convert to lowercase
        v = v.lower()
        # ---- Mold the entry into the expected format that includes a preceding 'epsg:'
        if not v.startswith("epsg"):
            v = "epsg:" + v
        # ---- Ensure that the colon is present
        if ":" not in v:
            v = "epsg:" + v.split("epsg")[1]
        # ---- Evaluate whether the pre-validator succeeded in finding an acceptable format
        if not re.match(r"^epsg:\d+$", v):
            raise ValueError(
                f"Echopop cannot parse the defined EPSG code ('{v}'). EPSG codes most be formatted "
                f"with strings beginning with 'epsg:' followed by the integer number code (e.g. "
                f"'epsg:4326')."
            )
        # ---- Return the pre-validated entry
        return v


class NASCExports(BaseModel, arbitrary_types_allowed=True):
    """
    NASC export processing parameters
    """

    export_file_directory: str
    nasc_export_directory: str
    save_file_template: str
    save_file_sheetname: str
    regions: Dict[str, List[str]]
    max_transect_spacing: realposfloat
    file_columns: List[str]

    @field_validator("max_transect_spacing", mode="before")
    def validate_realposfloat(cls, v):
        return realposfloat(v)

    @field_validator("save_file_template", mode="after")
    def validate_save_file_template(cls, v):
        # ---- Find all strings contained within curly braces
        template_ids = re.findall(r"{(.*?)}", v)
        # ---- Evaluate valid id's
        if not set(template_ids).issubset(set(["REGION", "YEAR", "GROUP"])):
            # ---- Get the unknown IDs
            unknown_ids = set(template_ids) - set(["REGION", "YEAR", "GROUP"])
            # ---- Raise Error
            raise ValueError(
                f"Haul-to-transect mapping save file template ({v}) contains invalid identifiers "
                f"({list(unknown_ids)}). Valid identifiers within the filename template (bounded "
                f"by curly braces) include: ['YEAR', 'REGION', 'GROUP']."
            )
        # ---- Return values
        return v


class CONFIG_INIT_MODEL(BaseModel, arbitrary_types_allowed=True):
    """
    Initialization parameter configuration YAML validator
    """

    stratified_survey_mean_parameters: StratifiedSurveyMeanParameters
    kriging_parameters: KrigingParameters
    bio_hake_age_bin: List[Union[posint, realposfloat]]
    bio_hake_len_bin: List[Union[posint, realposfloat]]
    TS_length_regression_parameters: Dict[str, TSLRegressionParameters]
    geospatial: Geospatial
    nasc_exports: Optional[NASCExports] = None
    haul_to_transect_mapping: Optional[HaulTransectMap] = None
    transect_region_mapping: Optional[TransectRegionMap] = None

    def __init__(self, filename, **kwargs):
        try:
            super().__init__(**kwargs)
        except ValidationError as e:
            # Customize error message
            new_message = str(e).replace(
                self.__class__.__name__, f"configuration parameters defined in {filename}"
            )
            raise ValueError(new_message) from e

    @field_validator("bio_hake_age_bin", "bio_hake_len_bin", mode="before")
    def validate_interval(cls, v):
        # ---- Check Union typing
        try:
            all(
                isinstance(value, (int, float))
                and (posint(value) if isinstance(value, int) else realposfloat(value))
                for value in v
            )
        except ValueError as e:
            raise ValueError(f"Invalid value detected within list. Every {str(e).lower()}")
        # ---- Check length
        if not len(v) == 3:
            raise ValueError(
                "Interval list must have a length of 3: "
                "['starting_value', 'ending_value', 'number']."
            )
        # ---- Check for any that may be 'realposfloat'
        any_posfloat = any(isinstance(value, (realposfloat, float)) for value in v)
        # ---- If true, then convert
        if any_posfloat:
            return [posint(value) if i == 2 else realposfloat(value) for i, value in enumerate(v)]
        else:
            return [posint(value) for value in v]


class XLSXFiles(BaseModel):
    """
    .xlsx file tree structure
    """

    filename: str
    sheetname: Union[str, List[str]]


class BiologicalFiles(BaseModel):
    """
    Biological data files
    """

    length: Union[Dict[str, XLSXFiles], XLSXFiles]
    specimen: Union[Dict[str, XLSXFiles], XLSXFiles]
    catch: Union[Dict[str, XLSXFiles], XLSXFiles]
    haul_to_transect: Union[Dict[str, XLSXFiles], XLSXFiles]


class KrigingFiles(BaseModel):
    """
    Kriging data files
    """

    vario_krig_para: XLSXFiles
    isobath_200m: XLSXFiles
    mesh: XLSXFiles


class StratificationFiles(BaseModel):
    """
    Stratification data files
    """

    strata: XLSXFiles
    geo_strata: XLSXFiles


class CONFIG_DATA_MODEL(BaseModel):
    """
    Data file configuration YAML validator
    """

    survey_year: int
    biological: BiologicalFiles
    stratification: StratificationFiles
    NASC: Dict[str, XLSXFiles]
    gear_data: Dict[str, XLSXFiles]
    kriging: KrigingFiles
    data_root_dir: Optional[str] = None
    CAN_haul_offset: Optional[int] = None
    ship_id: Optional[Union[int, str, float]] = None
    export_regions: Optional[Dict[str, XLSXFiles]] = None

    def __init__(self, filename, **kwargs):
        try:
            super().__init__(**kwargs)
        except ValidationError as e:
            # Customize error message
            new_message = str(e).replace(
                self.__class__.__name__, f"configured data files defined in {filename}"
            )
            raise ValueError(new_message) from e
        
class VariogramModel(BaseModel, arbitrary_types_allowed=True):
    """
    Base Pydantic model for variogram analysis inputs
    """

    # Factory method
    @classmethod
    def create(cls, **kwargs):
        """
        Factory creation method
        """
        try:
            return cls(**kwargs).model_dump(exclude_none=True)
        except ValidationError as e:
            e.__traceback__ = None
            raise e

class VariogramEmpirical(VariogramModel, arbitrary_types_allowed=True):
    """
    Empirical variogram parameters

    Parameters
    ----------
    azimuth_range: float
        The total azimuth angle range that is allowed for constraining
        the relative angles between spatial points, particularly for cases where a high degree
        of directionality is assumed.
    force_lag_zero: bool
        See the `variogram_parameters` argument in
        :fun:`echopop.spatial.variogram.empirical_variogram` for more details on
        `force_lag_zero`.
    standardize_coordinates: bool
        When set to `True`, transect coordinates are standardized using reference coordinates.

    Returns
    ----------
    VariogramEmpirical: A validated dictionary with the user-defined empirical variogram
    parameter values and default values for any missing parameters/keys.
    """

    azimuth_range: realcircle = Field(default=360.0, ge=0.0, le=360.0, allow_inf_nan=False)
    force_lag_zero: bool = Field(default=True)
    standardize_coordinates: bool = Field(default=True)

    @field_validator("azimuth_range", mode="before")
    def validate_realcircle(cls, v):
        return realcircle(v)
    
    def __init__(
        self,
        azimuth_range: realcircle = 360.0,
        force_lag_zero: bool = True,
        standardize_coordinates: bool = True,
        **kwargs,
    ):
        """
        Empirical variogram processing parameters
        """

        try:
            super().__init__(
                azimuth_range=azimuth_range,
                force_lag_zero=force_lag_zero,
                standardize_coordinates=standardize_coordinates,
            )
        except ValidationError as e:
            # Drop traceback
            e.__traceback__ = None
            raise e

class VariogramOptimize(VariogramModel, arbitrary_types_allowed=True):
    """
    Variogram optimization (non-linear least squares) parameters

    Parameters
    ----------
    max_fun_evaluations: posint
        The maximum number of evaluations. Defaults to 500.
    cost_fun_tolerance: realposfloat
        Threshold used for determining convergence via incremental changes of the cost function.
        Defaults to 1e-6.
    solution_tolerance: realposfloat
        Threshold used for determining convergence via change of the independent variables.
        Defaults to 1e-8.
    gradient_tolerance: realposfloat
        Threshold used for determining convergence via the gradient norma. Defaults to 1e-8.
    finite_step_size: realposfloat
        The relative step sizes used for approximating the Jacobian via finite differences.
    trust_region_solver: Literal["exact", "base"]
        The method used for solving the trust-region problem by either using the Jacobian
        computed from the first iteration (`"base"`) or via singular value decomposition
        (`"exact"`). Defaults to "exact".
    x_scale: Union[Literal["jacobian"], np.ndarray[realposfloat]]
        When `x_scale="jacobian"`, the characteristic scale is updated across numerical
        iterations via the inverse norms of the Jacobian matrix. Otherwise, a `np.ndarray`
        of the same length as `fit_parameters` can provide a constant scaling factor.
    jacobian_approx: Literal["forward", "central"]
        Indicates whether forward differencing (`"forward"`) or central differencing
        (`"central"`) should be used to approximate the Jacobian matrix.

    Returns
    ----------
    VariogramOptimize: A validated dictionary with the user-defined variogram optimizatization
    parameter values and default values for any missing parameters/keys.
    """
    max_fun_evaluations: posint = Field(default=500, gt=0, allow_inf_nan=False)
    cost_fun_tolerance: realposfloat = Field(default=1e-6, gt=0.0, allow_inf_nan=False)
    gradient_tolerance: realposfloat = Field(default=1e-6, gt=0.0, allow_inf_nan=False)
    solution_tolerance: realposfloat = Field(default=1e-8, gt=0.0, allow_inf_nan=False)
    finite_step_size: realposfloat = Field(default=1e-8, gt=0.0, allow_inf_nan=False)
    trust_region_solver: Literal["base", "exact"] = Field(default="exact")    
    x_scale: Union[Literal["jacobian"], np.ndarray[realposfloat]] = Field(default="jacobian")
    jacobian_approx: Literal["forward", "central"] = Field(default="central")

    @field_validator("max_fun_evaluations", mode="before")
    def validate_posint(cls, v):
        return posint(v)
    
    @field_validator("cost_fun_tolerance", "gradient_tolerance",
                     "finite_step_size", "solution_tolerance",
                       mode="before")
    def validate_realposfloat(cls, v):
        return realposfloat(v)

    @field_validator("x_scale", mode="before")
    def validate_xscale(cls, v):
        # Validate `np.ndarray[realposfloat]` case
        if isinstance(v, np.ndarray):
            # ---- Coerce values to a float
            v_float = [float(x) for x in v]
            # ---- Coerce to 'realposfloat', or raise Error
            try:
                v = np.array([realposfloat(x) for x in v_float])            
            except ValueError as e:
                e.__traceback__ = None
                raise e
        # Validate `Literal['jacobian']` case
        elif isinstance(v, (int, float, str)) and v != "jacobian":
            raise ValueError(
                "Input should be either the Literal 'jacobian' or a NumPy array of real positive-only float values."
            )
        # Return 'v'
        return v

class VariogramBase(VariogramModel, arbitrary_types_allowed=True):
    """
    Base variogram model parameters

    Parameters
    ----------
    model: Union[str, List[str]]
        A string or list of model names. A single name represents a single family model. Two
        inputs represent the desired composite model (e.g. the composite J-Bessel and
        exponential model). Defaults to: ['bessel', 'exponential']. Available models and their
        required arguments can be reviewed in the :fun:`echopop.spatial.variogram.variogram`
        function.
    n_lags: posint
        See the `variogram_parameters` argument in
        :fun:`echopop.spatial.variogram.empirical_variogram` for more details on
        `n_lags`.
    sill: Optional[realposfloat]
        See the description of `sill` in
        :fun:`echopop.spatial.variogram.variogram`.
    nugget: Optional[realposfloat]
        See the description of `nugget` in
        :fun:`echopop.spatial.variogram.variogram`.
    correlation_range: Optional[realposfloat]
        See the description of `correlation_range` in
        :fun:`echopop.spatial.variogram.variogram`.
    hole_effect_range: Optional[realposfloat]
        See the description of `hole_effect_range` in
        :fun:`echopop.spatial.variogram.variogram`.
    decay_power: Optional[realposfloat]
        See the description of `decay_power` in
        :fun:`echopop.spatial.variogram.variogram`.
    enhanced_semivariance: Optional[bool]
        See the description of `enhanced_semivariance` in
        :fun:`echopop.spatial.variogram.variogram`.

    Returns
    ----------
    VariogramBase: A validated dictionary with the user-defined variogram parameter values and
    default values for any missing parameters/keys.
    """
    model: Union[str, List[str]] = Field(union_mode="left_to_right")
    n_lags: posint = Field(ge=1, allow_inf_nan=False)
    lag_resolution: Optional[realposfloat] = Field(default=None, gt=0.0, allow_inf_nan=False)
    sill: Optional[realposfloat] = Field(default=None, ge=0.0, allow_inf_nan=False)
    nugget: Optional[realposfloat] = Field(default=None, ge=0.0, allow_inf_nan=False)
    hole_effect_range: Optional[realposfloat] = Field(default=None, ge=0.0, allow_inf_nan=False)
    correlation_range: Optional[realposfloat] = Field(default=None, ge=0.0, allow_inf_nan=False)
    enhance_semivariance: Optional[bool] = Field(default=None)
    decay_power: Optional[realposfloat] = Field(default=None, ge=0.0, allow_inf_nan=False)

    @field_validator("n_lags", mode="before")
    def validate_posint(cls, v):
        return posint(v)
    
    @field_validator("lag_resolution", "sill", "nugget", "hole_effect_range", "correlation_range", "decay_power",
                     mode="before")
    def validate_realposfloat(cls, v):
        return realposfloat(v)
class InitialValues(VariogramModel, arbitrary_types_allowed=True):    
    min: Optional[realposfloat] = Field(default=None)
    value: realposfloat = Field(default=0.0, allow_inf_nan=False)    
    max: Optional[posfloat] = Field(default=None)
    vary: bool = Field(default=False)
    """
    Variogram optimization initial values and ranges

    Parameters
    ----------
    min: Optional[realposfloat]
        Minimum value allowed during optimization.
    value: Optional[realposfloat]
        Starting value used for optimization.
    max: Optional[posfloat]
        Maximum value (including infinity) allowed during optimization.
    vary: Optional[bool]
        Boolean value dictating whether a particular parameter will be adjusted 
        during optimization ['True'] or held constant ['False']
    """

    @field_validator("min", "value", mode="before")
    def validate_realposfloat(cls, v):
        return realposfloat(v)
    
    @field_validator("max", mode="before")
    def validate_posfloat(cls, v):
        return posfloat(v)
    
    @model_validator(mode="after")
    def validate_value_sort(self):
        
        # Check whether the 'min' and 'max' keys exist
        min = getattr(self, "min", None)
        max = getattr(self, "max", None)
        value = getattr(self, "value", None)
        vary = getattr(self, "vary", None)
        # ---- Group into a dictionary
        value_dict = dict(min=min, value=value, max=max, vary=vary)

        # Evaluate case where 'vary = False'
        if not vary:
            updated_value_dict = InitialValues._DEFAULT_STRUCTURE_EMPTY({"value": value})
            # ---- Update 'min', 'value', 'max'
            self.min = None; self.max = None
            self.value = updated_value_dict["value"]
        
        # Evaluate case where 'vary = True' but 'min' and 'max' are not found
        if vary:
            updated_value_dict = InitialValues._DEFAULT_STRUCTURE_OPTIMIZE(
                {k: v for k, v in value_dict.items() if v is not None}
            )
            # ---- Update 'min', 'value', 'max'
            self.min = updated_value_dict["min"]
            self.value = updated_value_dict["value"]
            self.max = updated_value_dict["max"]

            # Ensure valid min-value-max grouping
            # ---- Only apply if parameters are being varied
            if (
                not (self.min <= self.value <= self.max) and self.vary
            ):
                # ---- Raise Error
                raise ValueError(
                    "Optimization minimum, starting, and maximum values  must satisfy the logic: "
                    "`min` <= value` <= `max`."
                )
            
        # Return values
        return self
    
    @classmethod
    def _DEFAULT_STRUCTURE_EMPTY(cls, input: Dict[str, Any] = {}):
        return {**dict(vary=False), **input}
    
    @classmethod
    def _DEFAULT_STRUCTURE_OPTIMIZE(cls, input: Dict[str, Any] = {}):
        return {**dict(min=0.0, value=0.0, max=np.inf, vary=True), **input}


class VariogramInitial(RootModel[InitialValues]):
    root: Dict[str, InitialValues]

    @model_validator(mode="before")
    @classmethod
    def validate_model_params(cls, v):
        
        # Get valid parameters
        valid_param_names = cls._VALID_PARAMETERS()

        # Compare names of input versus those that are accepted
        if not set(v).issubset(valid_param_names):
            # ---- Get unexpected parameter names
            unexpected = set(v) - set(valid_param_names)
            # ---- Raise Error
            raise ValueError(
                f"Unexpected optimization parameters: {list(unexpected)}. Only the "
                f"following variogram parameters are valid for optimization: "
                f"{valid_param_names}."
            )
        
        # Return values otherwise
        return v
    
    @classmethod
    def _VALID_PARAMETERS(cls):
        return ["correlation_range", "decay_power", "hole_effect_range", "nugget", "sill"]
    
    @classmethod
    def create(cls, **kwargs):
        """
        Factory creation method
        """
        try:
            return cls(**kwargs).model_dump(exclude_none=True)
        except ValidationError as e:
            e.__traceback__ = None
            raise e



class MeshCrop(
    BaseModel,
    arbitrary_types_allowed=True,
    title="kriging mesh cropping parameters ('cropping_parameters')",
):
    crop_method: Literal["transect_ends", "convex_hull"] = Field(default="transect_ends")
    num_nearest_transects: posint = Field(gt=0, default=4)
    mesh_buffer_distance: realposfloat = Field(gt=0.0, default=1.25, allow_inf_nan=False)
    latitude_resolution: realposfloat = Field(gt=0.0, default=1.25, allow_inf_nan=False)
    bearing_tolerance: realcircle = Field(gt=0.0, default=15.0, le=180.0, allow_inf_nan=False)

    @field_validator("num_nearest_transects", mode="before")
    def validate_posint(cls, v):
        return posint(v)

    @field_validator("bearing_tolerance", mode="before")
    def validate_realcircle(cls, v):
        return realcircle(v)

    @field_validator("mesh_buffer_distance", "latitude_resolution", mode="before")
    def validate_realposfloat(cls, v):
        return realposfloat(v)

    def __init__(
        self,
        crop_method: Literal["transect_ends", "convex_hull"] = "transect_ends",
        num_nearest_transects: posint = 4,
        mesh_buffer_distance: realposfloat = 1.25,
        latitude_resolution: realposfloat = 1.25,
        bearing_tolerance: realcircle = 15.0,
        **kwargs,
    ):
        """
        Mesh cropping method parameters
        """

        try:
            super().__init__(
                crop_method=crop_method,
                num_nearest_transects=num_nearest_transects,
                mesh_buffer_distance=mesh_buffer_distance,
                latitude_resolution=latitude_resolution,
                bearing_tolerance=bearing_tolerance,
            )
        except ValidationError as e:
            # Drop traceback
            e.__traceback__ = None
            raise e

    # Factory method
    @classmethod
    def create(cls, **kwargs):
        """
        Factory creation method to create a `MeshCrop` instance
        """
        return cls(**kwargs).model_dump(exclude_none=True)


class KrigingParameterInputs(
    BaseModel, arbitrary_types_allowed=True, title="kriging model parameters ('kriging_parameters')"
):
    anisotropy: realposfloat = Field(default=0.0, allow_inf_nan=False)
    kmin: posint = Field(default=3, ge=3)
    kmax: posint = Field(default=10, ge=3)
    correlation_range: Optional[realposfloat] = Field(default=None, gt=0.0, allow_inf_nan=False)
    search_radius: Optional[realposfloat] = Field(default=None, gt=0.0, allow_inf_nan=False)

    @field_validator("kmin", "kmax", mode="before")
    def validate_posint(cls, v):
        return posint(v)

    @field_validator("anisotropy", "correlation_range", "search_radius", mode="before")
    def validate_realposfloat(cls, v):
        if v is None:
            return v
        else:
            return realposfloat(v)

    @model_validator(mode="before")
    def validate_k_window(cls, values):
        # ---- Get `kmin`
        kmin = values.get("kmin", 3)
        # ---- Get 'kmax'
        kmax = values.get("kmax", 10)
        # ---- Ensure that `kmax >= kmin`
        if kmax < kmin:
            # ---- Raise Error
            raise ValueError(
                f"Defined 'kmax' ({kmax}) must be greater than or equal to 'kmin' ({kmin})."
            )
        # ---- Return values
        return values

    @model_validator(mode="before")
    def validate_spatial_correlation_params(cls, values):
        # ---- Get `correlation_range`
        correlation_range = values.get("correlation_range", None)
        # ---- Get 'search_radius'
        search_radius = values.get("search_radius", None)
        # ---- Ensure that both parameters are not None
        if not correlation_range and not search_radius:
            # ---- Raise Error
            raise ValueError(
                "Both 'correlation_range' and 'search_radius' arguments are missing. At least one "
                "must be defined."
            )
        # ---- Return values
        return values

    # Factory method
    @classmethod
    def create(cls, **kwargs):
        """
        Factory creation method to create a `KrigingParameters` instance
        """

        # Collect errors, if any arise
        try:
            # ---- Test validate
            _ = cls(**kwargs)
            # ---- Edit values if needed
            if kwargs.get("search_radius") is None and kwargs["correlation_range"] is not None:
                kwargs["search_radius"] = kwargs["correlation_range"] * 3
            # ---- Produce the dictionary as an output
            return cls(**kwargs).model_dump(exclude_none=True)
        except ValidationError as e:
            e.__traceback__ = None
            raise e


class KrigingAnalysis(BaseModel, arbitrary_types_allowed=True):
    best_fit_variogram: bool = Field(default=False)
    coordinate_transform: bool = Field(default=True)
    extrapolate: bool = Field(default=False)
    variable: Literal["biomass"] = Field(default="biomass")
    verbose: bool = Field(default=True)

    def __init__(self, **kwargs):
        try:
            super().__init__(**kwargs)
        except ValidationError as e:
            # Drop traceback
            e.__traceback__ = None
            raise e

    # Factory method
    @classmethod
    def create(cls, **kwargs):
        """
        Factory creation method to create a `KrigingAnalysis` instance
        """
        return cls(**kwargs).model_dump(exclude_none=True)
