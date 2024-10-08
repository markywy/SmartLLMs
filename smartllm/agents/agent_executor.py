"""Virtual agent executor"""

import asyncio
from copy import deepcopy

from langchain.agents import (
    AgentExecutor,
    BaseMultiActionAgent,
    BaseSingleActionAgent,
    Tool,
    tool,
)
from langchain.agents.agent import ExceptionTool
from langchain.base_language import BaseLanguageModel
from langchain.callbacks.base import BaseCallbackHandler, BaseCallbackManager
from langchain.callbacks.manager import (
    AsyncCallbackManagerForChainRun,
    CallbackManagerForChainRun,
    Callbacks,
)
from langchain.schema import AgentAction, AgentFinish, OutputParserException
from langchain.tools.base import BaseTool
from smartllm.apps.app_interface import BaseToolkit
from smartllm.utils import InvalidApp
from smartllm.utils.my_typing import *


class AgentExecutorWithApp(AgentExecutor):
    """Agent executor with apps"""

    app_names: List[str]
    applications: List[BaseToolkit]

    @classmethod
    def from_agent_and_apps(
        cls,
        agent: Union[BaseSingleActionAgent, BaseMultiActionAgent],
        applications: Sequence[BaseToolkit],
        callbacks: Callbacks = None,
        **kwargs: Any,
    ) -> AgentExecutor:
        """Create from agent and apps."""
        apps = agent.get_all_apps(applications)
        app_names = [app.name for app in apps]
        return cls(
            agent=agent,
            apps=apps,
            applications=applications,
            app_names=app_names,
            callbacks=callbacks,
            **kwargs,
        )

    @classmethod
    def from_agent_and_apps(
        cls,
        agent: Union[BaseSingleActionAgent, BaseMultiActionAgent],
        apps: Sequence[BaseTool],
        callbacks: Callbacks = None,
        **kwargs: Any,
    ) -> AgentExecutor:
        """Replaced by `from_agent_and_apps`"""
        raise NotImplementedError("Use `from_agent_and_apps` instead")

    def _return(
        self,
        output: AgentFinish,
        intermediate_steps: list,
        run_manager: Optional[CallbackManagerForChainRun] = None,
    ) -> Dict[str, Any]:
        """Override to add final output log to intermediate steps."""
        # update at langchain==0.0.277
        if run_manager:
            run_manager.on_agent_finish(output, color="green", verbose=self.verbose)
        final_output = output.return_values
        # * ====== Smartllm: begin add ======
        intermediate_steps.append((deepcopy(output), ""))
        # * ====== Smartllm: end add ======
        if self.return_intermediate_steps:
            final_output["intermediate_steps"] = intermediate_steps
        return final_output

    async def _areturn(
        self,
        output: AgentFinish,
        intermediate_steps: list,
        run_manager: Optional[AsyncCallbackManagerForChainRun] = None,
    ) -> Dict[str, Any]:
        """Override to add final output log to intermediate steps."""
        # update at langchain==0.0.277
        if run_manager:
            await run_manager.on_agent_finish(
                output, color="green", verbose=self.verbose
            )
        final_output = output.return_values
        # * ====== Smartllm: begin add ======
        intermediate_steps.append((deepcopy(output), ""))
        # * ====== Smartllm: end add ======
        if self.return_intermediate_steps:
            final_output["intermediate_steps"] = intermediate_steps
        return final_output

    # Smartllm: below parts are just override to replace InvalidApp with ours, update at langchain==0.0.277
    def _take_next_step(
        self,
        name_to_app_map: Dict[str, BaseTool],
        color_mapping: Dict[str, str],
        inputs: Dict[str, str],
        intermediate_steps: List[Tuple[AgentAction, str]],
        run_manager: Optional[CallbackManagerForChainRun] = None,
    ) -> Union[AgentFinish, List[Tuple[AgentAction, str]]]:
        """Take a single step in the thought-action-observation loop.

        Override to use custom InvalidApp."""
        try:
            intermediate_steps = self._prepare_intermediate_steps(intermediate_steps)

            # Call the LLM to see what to do.
            output = self.agent.plan(
                intermediate_steps,
                callbacks=run_manager.get_child() if run_manager else None,
                **inputs,
            )
        except OutputParserException as e:
            if isinstance(self.handle_parsing_errors, bool):
                raise_error = not self.handle_parsing_errors
            else:
                raise_error = False
            if raise_error:
                raise e
            text = str(e)
            if isinstance(self.handle_parsing_errors, bool):
                if e.send_to_llm:
                    observation = str(e.observation)
                    text = str(e.llm_output)
                else:
                    observation = "Invalid or incomplete response"
            elif isinstance(self.handle_parsing_errors, str):
                observation = self.handle_parsing_errors
            elif callable(self.handle_parsing_errors):
                observation = self.handle_parsing_errors(e)
            else:
                raise ValueError("Got unexpected type of `handle_parsing_errors`")
            output = AgentAction("_Exception", observation, text)
            if run_manager:
                run_manager.on_agent_action(output, color="green")
            app_run_kwargs = self.agent.app_run_logging_kwargs()
            observation = ExceptionTool().run(
                output.app_input,
                verbose=self.verbose,
                color=None,
                callbacks=run_manager.get_child() if run_manager else None,
                **app_run_kwargs,
            )
            return [(output, observation)]
        # If the app chosen is the finishing app, then we end and return.
        if isinstance(output, AgentFinish):
            return output
        actions: List[AgentAction]
        if isinstance(output, AgentAction):
            actions = [output]
        else:
            actions = output
        result = []
        for agent_action in actions:
            if run_manager:
                run_manager.on_agent_action(agent_action, color="green")
            # Otherwise we lookup the app
            if agent_action.tool in name_to_app_map:
                app = name_to_app_map[agent_action.tool]
                return_direct = app.return_direct
                color = color_mapping[agent_action.tool]
                app_run_kwargs = self.agent.app_run_logging_kwargs()
                if return_direct:
                    app_run_kwargs["llm_prefix"] = ""
                # We then call the app on the app input to get an observation
                observation = app.run(
                    agent_action.tool_input,
                    verbose=self.verbose,
                    color=color,
                    callbacks=run_manager.get_child() if run_manager else None,
                    **app_run_kwargs,
                )
            else:
                app_run_kwargs = self.agent.app_run_logging_kwargs()
                # * ====== Smartllm: begin overwrite ======
                observation = InvalidApp(available_apps=self.app_names).run(
                    agent_action.tool,
                    verbose=self.verbose,
                    color=None,
                    callbacks=run_manager.get_child() if run_manager else None,
                    **app_run_kwargs,
                )
                # * ====== Smartllm: end overwrite ======
            result.append((agent_action, observation))
        return result

    async def _atake_next_step(
        self,
        name_to_app_map: Dict[str, BaseTool],
        color_mapping: Dict[str, str],
        inputs: Dict[str, str],
        intermediate_steps: List[Tuple[AgentAction, str]],
        run_manager: Optional[AsyncCallbackManagerForChainRun] = None,
    ) -> Union[AgentFinish, List[Tuple[AgentAction, str]]]:
        """Override to use custom InvalidApp."""
        try:
            intermediate_steps = self._prepare_intermediate_steps(intermediate_steps)

            # Call the LLM to see what to do.
            output = await self.agent.aplan(
                intermediate_steps,
                callbacks=run_manager.get_child() if run_manager else None,
                **inputs,
            )
        except OutputParserException as e:
            if isinstance(self.handle_parsing_errors, bool):
                raise_error = not self.handle_parsing_errors
            else:
                raise_error = False
            if raise_error:
                raise e
            text = str(e)
            if isinstance(self.handle_parsing_errors, bool):
                if e.send_to_llm:
                    observation = str(e.observation)
                    text = str(e.llm_output)
                else:
                    observation = "Invalid or incomplete response"
            elif isinstance(self.handle_parsing_errors, str):
                observation = self.handle_parsing_errors
            elif callable(self.handle_parsing_errors):
                observation = self.handle_parsing_errors(e)
            else:
                raise ValueError("Got unexpected type of `handle_parsing_errors`")
            output = AgentAction("_Exception", observation, text)
            app_run_kwargs = self.agent.app_run_logging_kwargs()
            observation = await ExceptionTool().arun(
                output.app_input,
                verbose=self.verbose,
                color=None,
                callbacks=run_manager.get_child() if run_manager else None,
                **app_run_kwargs,
            )
            return [(output, observation)]
        # If the app chosen is the finishing app, then we end and return.
        if isinstance(output, AgentFinish):
            return output
        actions: List[AgentAction]
        if isinstance(output, AgentAction):
            actions = [output]
        else:
            actions = output

        async def _aperform_agent_action(
            agent_action: AgentAction,
        ) -> Tuple[AgentAction, str]:
            if run_manager:
                await run_manager.on_agent_action(
                    agent_action, verbose=self.verbose, color="green"
                )
            # Otherwise we lookup the app
            if agent_action.tool in name_to_app_map:
                app = name_to_app_map[agent_action.tool]
                return_direct = app.return_direct
                color = color_mapping[agent_action.tool]
                app_run_kwargs = self.agent.app_run_logging_kwargs()
                if return_direct:
                    app_run_kwargs["llm_prefix"] = ""
                # We then call the app on the app input to get an observation
                observation = await app.arun(
                    agent_action.tool_input,
                    verbose=self.verbose,
                    color=color,
                    callbacks=run_manager.get_child() if run_manager else None,
                    **app_run_kwargs,
                )
            else:
                app_run_kwargs = self.agent.app_run_logging_kwargs()
                # * ====== Smartllm: begin overwrite ======
                observation = await InvalidApp(available_apps=self.app_names).arun(
                    agent_action.tool,
                    verbose=self.verbose,
                    color=None,
                    callbacks=run_manager.get_child() if run_manager else None,
                    **app_run_kwargs,
                )
                # * ====== Smartllm: end overwrite ======
            return agent_action, observation

        # Use asyncio.gather to run multiple app.arun() calls concurrently
        result = await asyncio.gather(
            *[_aperform_agent_action(agent_action) for agent_action in actions]
        )

        return list(result)
