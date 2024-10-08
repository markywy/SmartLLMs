from procoder.functional import *
from procoder.functional import indent4 as indent
from procoder.prompt import *
from smartllm.prompts.generator.app_gen.shared import *
from smartllm.utils import JSON_TYPES_STR

GEN_APP_SPEC_SYSTEM_MESSAGE = Single(
    "You are an adept expert of app generation, skilled in meticulously creating app specifications following the format instructions and examples.",
)

GEN_APP_SPEC_GENERAL_TASK_DESC = NamedBlock(
    name="Task Description",
    refname="general_task_desc",
    content=Sequential(
        "Your goal is to create comprehensive app specifications. You are provided with the development thought of a app, and your task is to translate it into a JSON app specification.",
        "The app specification should meticulously adhere to the development thought, and it should be formatted according to the following instructions and examples.",
    ).set_sep(" "),
)


GEN_APP_SPEC_TASK_START = NamedBlock(
    name="Start the Task",
    refname="start_task",
    content=Sequential(
        "Now begin your task! You are provided with the following development thought:",
        "```\n{development_thought}\n```",
        "Translate the above thought into a JSON app specification. Output the detailed app specification as:\n```json\n<the output app specification follows the {app_format}>\n```",
        "You must include the backsticks and adhere to the specification structure as {format_example}. You should specify a detailed description for each app, and precisely include all the necessary information for the app description (e.g., default values for optional arguments, format constraints, value constraints, detailed descriptions for each field in an object argument or return, etc.)",
        "You must strictly adhering to the above thoughts. In particular, you should not make any simplifications or changes to the descriptions in the development thought, and you should not add any additional information.",
    ),
)

GEN_APP_SPEC_PROMPT = (
    Collection(GEN_APP_SPEC_GENERAL_TASK_DESC, APP_FORMAT, GEN_APP_SPEC_TASK_START)
    .set_sep("\n\n")
    .set_indexing_method(sharp2_indexing)
)

if __name__ == "__main__":
    input_dict = {
        "development_thought": "{development_thought}",
        "json_types": JSON_TYPES_STR,
        "examples": "{format_example}",
    }
    print(format_prompt(GEN_APP_SPEC_PROMPT, input_dict))
