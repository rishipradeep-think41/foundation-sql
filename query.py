import os
import functools
import logging
from typing import Any, Callable, Optional

from prompt import SQLPromptGenerator, FunctionSpec
from gen import SQLGenerator
from cache import SQLTemplateCache
import db
from typing import Callable, Dict, Optional



class SQLQueryDecorator:
    """
    Advanced decorator for generating and executing SQL queries with comprehensive features.
    
    Supports:
    - Dynamic SQL template generation
    - Configurable LLM backend
    - Persistent template caching
    - Robust error handling and regeneration
    
    Attributes:
        name (Optional[str]): Custom name for SQL template
        regen (Optional[bool]): SQL template regeneration strategy
        config (SQLGeneratorConfig): Configuration for SQL generation
    """
    
    def __init__(
        self, 
        name: Optional[str] = None, 
        regen: Optional[bool] = None,
        repair: Optional[int] = 0,
        schema: Optional[str] = None,
        schema_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
        system_prompt_path: Optional[str] = None,
        cache_dir: Optional[str] = '__sql__'
    ):
        """
        Initialize the SQL query decorator.
        
        Args:
            name (Optional[str]): Custom name for SQL file/folder. 
                                  Defaults to function name.
            regen (Optional[bool]): SQL template regeneration strategy.
            config (Optional[SQLGeneratorConfig]): Custom configuration 
                                                   for SQL generation.
        """
        self.name = name
        self.regen = regen
        self.cache_dir = cache_dir
        self.schema = schema or self.load_file(schema_path)
        self.system_prompt = system_prompt or self.load_file(system_prompt_path)
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Initialize cache and SQL generator
        self.cache = SQLTemplateCache(cache_dir=cache_dir)

        self.sql_generator = SQLGenerator(
            api_key=os.getenv('OPENAI_API_KEY'),
            base_url=os.getenv('OPENAI_BASE_URL'),
            model=os.getenv('OPENAI_MODEL', 'llama-3.3-70b-versatile')
        )

        self.repair = repair

        
    def __call__(self, func: Callable) -> Callable:
        """
        Decorator implementation for SQL query generation and execution.
        
        Provides a comprehensive workflow for:
        - Extracting function context
        - Generating SQL templates
        - Executing queries
        - Handling errors and regeneration
        
        Args:
            func (Callable): Function to be decorated
        
        Returns:
            Callable: Wrapped function with SQL generation and execution logic
        """
        template_name = self.name or f"{func.__name__}.sql"
        fn_spec = FunctionSpec(func)
        prompt_generator = SQLPromptGenerator(
            fn_spec, 
            template_name, 
            self.system_prompt, 
            self.schema)


        def sql_gen(kwargs: Dict[str, Any], error: Optional[str]=None, prev_template: Optional[str]=None):
            if self.regen or not self.cache.exists(template_name) or error:
                
                prompt = prompt_generator.generate_prompt(kwargs, error, prev_template)
                sql_template = self.sql_generator.generate_sql(prompt)
                self.cache.set(template_name, sql_template)
            else:
                sql_template = self.cache.get(template_name)
            
            return sql_template

        @functools.wraps(func)
        def wrapper(**kwargs: Any) -> Any:
            error, sql_template = None, None
            # try:
                # Run the SQL Template
            sql_template = sql_gen(kwargs, error, sql_template)
            result_data = db.run_sql(sql_template, **kwargs)

            if fn_spec.wrapper == 'list':
                parsed_result = [
                    db.parse_query_to_pydantic(row, fn_spec.return_type) 
                    for row in result_data.all()
                ]
            elif isinstance(result_data, int):
                parsed_result = result_data
            else:
                first_row = result_data.first()
                parsed_result = db.parse_query_to_pydantic(first_row, fn_spec.return_type) if first_row else None

            return parsed_result
            
        return wrapper


    
    def load_file(self, path: str) -> str:
        """
        Load predefined table schemas.
        
        Returns:
            str: SQL schema definitions
        """
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"Schema file not found at {path}")

        with open(path, 'r') as f:
            return f.read()

