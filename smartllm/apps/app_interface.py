"""App interface"""
from abc import abstractmethod

from langchain.agents import Tool
from langchain.tools import BaseTool
from pydantic import BaseModel, Field, validator
from smartllm.utils import (
    PRIMITIVE_TYPES,
    ArgException,
    ArgParameter,
    ArgReturn,
    create_str,
    insert_indent,
    load_dict,
    validate_inputs,
)
from smartllm.utils.my_typing import *


class FunctionApp(BaseTool):
    """
    Function app is defined according to our specifciation that resembles Python function docstring, see `app_interface.md`.
    """

    name: str = None
    summary: str = None
    parameters: List[ArgParameter] = None
    returns: List[ArgReturn] = None
    exceptions: List[ArgException] = None
    description: str = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.description is None and self.summary:
            self.description = self.create_description()

    def create_description(self, detail_level="high") -> str:
        # create a description for the app, including the parameters and return values
        # we use the Python docstring format
        if detail_level not in ["none", "low", "medium", "high"]:
            raise ValueError(
                f"detail_level must be one of 'none', 'low', 'medium', 'high'"
            )
        include_args_returns = detail_level in ["low", "medium", "high"]
        include_desc = detail_level in ["medium", "high"]
        include_exceptions = detail_level in ["high"]

        def get_combined_desc(name, items):
            prefix = f"  {name}:"
            item_strs = [create_str(item, include_desc=include_desc) for item in items]
            if include_desc:
                desc = prefix + "\n" + "\n".join(item_strs) + "\n"
            else:
                desc = prefix + " " + ", ".join(item_strs) + "\n"
            return desc

        desc = self.summary.rstrip("., ") + "\n"

        if include_args_returns:
            desc += get_combined_desc("Arguments", self.parameters)
            desc += get_combined_desc("Returns", self.returns)
            if include_exceptions:
                desc += get_combined_desc("Exceptions", self.exceptions)

        return desc

    def parse_parameters(self, app_input: str) -> Dict[str, Any]:
        """Parse the input string into a dictionary of parameters"""
        params = load_dict(app_input)
        validate_inputs(self.parameters, params)
        return params

    @abstractmethod
    def parse_return(self, app_output: Dict[str, Any]) -> str:
        """Parse the output dictionary into a string"""

    @abstractmethod
    def _runapp(self, app_input: Dict[str, Any]) -> Dict[str, Any]:
        """Run the app"""

    @abstractmethod
    def _arunapp(self, app_input: Dict[str, Any]) -> Dict[str, Any]:
        """Run the app asynchronously"""

    def _process(self, run_func: Callable, app_input: str) -> str:
        try:
            inputs = self.parse_parameters(app_input)
        except Exception as e:
            return f"Invalid Action Input: {e}"
        outputs = run_func(inputs)
        return self.parse_return(outputs)

    def _run(self, app_input: str) -> str:
        return self._process(self._runapp, app_input)

    def _arun(self, app_input: str) -> str:
        return self._process(self._arunapp, app_input)


class VirtualFunctionApp(FunctionApp):
    """Virtual function app that does not require implemented"""

    def __init__(self, name_prefix: str = "", app_spec: Dict[str, Any] = {}, **kwargs):
        super().__init__(**kwargs)
        for k, v in app_spec.items():
            if k == "name":
                v = name_prefix + v
            if k not in self.__dict__:
                raise ValueError(f"Invalid key {k} in app spec")
            setattr(self, k, v)
        if self.description is None:
            self.description = self.create_description()

    def parse_return(self, app_output: Dict[str, Any]) -> str:
        # parse the output dictionary into a string
        pass

    def _runapp(self, app_input: Dict[str, Any]) -> Dict[str, Any]:
        # run the app
        pass

    def _arunapp(self, app_input: Dict[str, Any]) -> Dict[str, Any]:
        # run the app asynchronously
        pass


class BaseToolkit:
    """
    The app consists of a collection of apps that are `BaseTool` objects.
    An example is a `Gmail` app that may have multiple app APIs, such as `Send`, `Read`, etc.
    """

    name: str
    app_classes: List[Any]

    def __init__(self):
        self.apps = self.load_tools()

    @abstractmethod
    def load_tools(self) -> List[BaseTool]:
        """Load the apps"""

    def _get_app_summary(self) -> str:
        name = self.app_marker(self.name)
        return f"{name} app: contain the following app APIs:\n"

    def create_description(self, detail_level: str) -> str:
        # create a description for the app, including the apps
        desc = self._get_app_summary()
        for app in self.apps:
            app_name = self.appapi_marker(app.name)
            app_desc = (
                app.create_description(detail_level)
                if isinstance(app, FunctionApp)
                else app.description
            )
            app_desc = insert_indent(app_desc, insert_first=False)
            desc += f"\t* {app_name}: {app_desc}"
        return desc

    @property
    def description(self) -> str:
        return self.create_description("high")

    @staticmethod
    def app_marker(s) -> str:
        """Get the app marker"""
        return f"<{s}>"

    @staticmethod
    def appapi_marker(s) -> str:
        """Get the app API marker"""
        # return f"[{s}]"
        return s

    def get_app(self, app_name: str) -> BaseTool:
        """Get a app by its name"""
        for app in self.apps:
            if app.name == app_name:
                return app
        raise ValueError(f"App {app_name} does not exist in this app")

    def __getitem__(self, app_name: str) -> BaseTool:
        """Get a app by its name"""
        return self.get_app(app_name)

    def __contains__(self, app_name: str) -> bool:
        """Check if a app exists in the app"""
        for app in self.apps:
            if app.name == app_name:
                return True
        return False

    def __iter__(self):
        """Iterate over the apps"""
        for app in self.apps:
            yield app

    def __len__(self):
        """Get the number of apps"""
        return len(self.apps)

    def __repr__(self):
        """Get the representation of the app"""
        return f"<App {self.name} with {len(self.apps)} apps>"

    def __str__(self):
        """Get the string representation of the app"""
        return self.__repr__()


class FunctionApp(BaseToolkit):
    """
    Function app consists of a collection of apps that are `FunctionAppAPI` objects.
    Defined according to our specifciation that resembles OpenAPI spec, see `app_interface.md`
    """

    name_for_human: str
    description_for_human: str
    name_for_model: str
    description_for_model: str
    app_classes: List[Any]

    def __init__(self):
        super().__init__()
        self.name = self.name_for_model

    def load_tools(self) -> List[BaseTool]:
        """Load the apps"""
        return [app_class() for app_class in self.app_classes]

    def _get_app_summary(self) -> str:
        app_name = self.app_marker(self.name_for_model)
        desc = f"{app_name}: {self.description_for_model}\n"
        desc += f"App APIs:\n"
        return desc
