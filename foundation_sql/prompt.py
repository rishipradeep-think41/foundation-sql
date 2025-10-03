import inspect
import json
from types import NoneType
from typing import Any, Callable, Dict, Optional, Type, Union, get_type_hints
from datetime import datetime

from pydantic import BaseModel


class FunctionSpec:

    def __init__(self, func: Callable):
        """
        Extract function specification details.

        Args:
            func (Callable): Function to analyze
        """
        self.name = func.__name__
        self.return_type, self.wrapper = self._extract_return_model(func)
        self.signature = inspect.signature(func)


        self.docstring = inspect.getdoc(func) or ""
        self.model_fields =   self._model_fields()

    def _model_fields(self):
        if self.return_type in [NoneType, int, str, bool]:
            return {}
        return {k: str(v) for k, v in self.return_type.model_fields.items()}


    def _extract_kwargs(self, func: Callable) -> Dict[str, Type]:
        """
        Extract named parameters and their types from a function.

        Args:
            func (Callable): Function to analyze

        Returns:
            Dict of parameter names and their types
        """
        signature = inspect.signature(func)
        return {
            name: param.annotation 
            for name, param in signature.parameters.items() 
            if param.annotation is not param.empty
        }

    def kwargs_json(self, kwargs: Dict[str, Any]):
        def serialize_value(v):
            if isinstance(v, BaseModel):
                # Recursively convert nested BaseModel objects to dictionaries
                model_dict = {}
                for field_name, field_value in v.model_dump(mode="json").items():
                    if isinstance(field_value, dict):
                        model_dict[field_name] = field_value
                    elif field_value is not None:
                        model_dict[field_name] = field_value
                return model_dict
            if isinstance(v, datetime):  # Handle datetime-like objects
                return v.isoformat()
            return v

        return json.dumps({k: serialize_value(v) for k, v in kwargs.items()}, indent=2)

    def _extract_return_model(self, func: Callable) -> (Type[BaseModel], Optional[str]):
        """
        Extract the return model type from a function's type annotations.
        
        Args:
            func (Callable): Function to analyze
        
        Returns:
            Tuple containing:
            - Pydantic model class
            - Wrapper type ('list' or None)
        
        Raises:
            ValueError: If return type is invalid or not a Pydantic model
        """
        hints = get_type_hints(func)
        if 'return' not in hints:
            raise ValueError(f'Function {func.__name__} must have a return type annotation')
        
        return_type = hints['return']
        wrapper = None
        
        # Handle Optional[Model]
        if hasattr(return_type, '__origin__') and return_type.__origin__ is Union:
            args = return_type.__args__
            if len(args) == 2 and args[1] is type(None):
                return_type = args[0]
        
        # Handle List[Model]
        if hasattr(return_type, '__origin__') and return_type.__origin__ is list:
            wrapper = 'list'
            return_type = return_type.__args__[0]
        
        return return_type, wrapper



class SQLPromptGenerator:
    """
    Generates prompts for SQL template generation based on function context and predefined schemas.
    
    Attributes:
        func (FunctionSpec): Function to generate SQL for
        template_name (str): Name of the SQL template
    """
    
    def __init__(self, func_spec: FunctionSpec, 
        template_name: str,
        system_prompt: str,
        schema: Optional[str] = None
        ):
        """
        Initialize the SQL prompt generator.
        
        Args:
            func (FunctionSpec): Function to generate SQL for
            template_name (str): Name of the SQL template
            system_prompt (str): System prompt for SQL generation
            schema (Optional[str]): SQL schema definitions
            error_prompt (Optional[str]): Error prompt for SQL generation
        """
        self.func_spec = func_spec
        self.template_name = template_name
        self.schema = schema
        self.system_prompt = system_prompt

    def generate_prompt(self, kwargs: Dict[str, Any], error: Optional[str] = None, prev_template: Optional[str] = None) -> str:
        """
        Generate a comprehensive prompt for SQL template generation.
        
        Returns:
            str: Detailed prompt with function context and schema
        """
        error_prompt = ""
        if error:
            error_prompt = f"""

We ran the above and it generated the following SQL:
{prev_template}

When running it, following error was encountered:
{error}

Review the error and suggest an improved SQL template that works.
"""

        
        return f"""
{self.system_prompt}
----------------
Available Tables Schema:
{self.schema}
----------------
Function Name: {self.func_spec.name}
Function Signature: {self.func_spec.signature}
Function Docstring: {self.func_spec.docstring}
Function Arguments: {self.func_spec.kwargs_json(kwargs)}

Return model: {self.func_spec.return_type.__name__}
Model fields: {json.dumps({k: str(v) for k, v in self.func_spec.model_fields.items()}, indent=2)}

----------------
{error_prompt}
"""
