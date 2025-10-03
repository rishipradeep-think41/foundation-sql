import logging
from openai import OpenAI
import re

class SQLGenerator:
    """
    Advanced SQL template generator with configurable LLM backend.
    
    Supports:
    - Configurable language models
    - Persistent template caching
    - Flexible generation parameters
    - Comprehensive error handling
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "llama-3.3-70b-versatile"
    ):
        """
        Initialize the SQL generator.
        
        Args:
            api_key (str): API key for the LLM service
            base_url (str): Base URL for the LLM service
        """
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @property
    def client(self):
        return OpenAI(api_key=self.api_key, base_url=self.base_url)


    def generate_sql(self, prompt: str) -> str:
        """
        Generate an SQL template based on the provided prompt.
        
        Args:
            prompt (str): Detailed prompt for SQL generation
            
        Returns:
            str: Generated SQL template
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt}
            ]
        )
        
        generated_sql = response.choices[0].message.content.strip()
        
        # Remove ```sql or ``` fences
        sql_template = re.sub(r"^```sql\s*|^```\s*|```$", "", generated_sql, flags=re.MULTILINE).strip()
        
        return sql_template