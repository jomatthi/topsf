# coding: utf-8

import luigi
import law
import os

from columnflow.tasks.framework.base import Requirements
from columnflow.tasks.framework.remote import RemoteWorkflow
from topsf.tasks.inference import CreateDatacards

from topsf.tasks.inference_v2.combine_base import CombineBaseTask
from topsf.tasks.inference_v2.workspace import CreateWorkspaceV2
from topsf.tasks.inference_v2.gen_toys import GenToysV2


class ImpactsV2(
    CombineBaseTask,
):
    mass = luigi.IntParameter(
        significant=True,
        description="Mass point",
    )

    robust_fit = luigi.IntParameter(
        significant=False,
        description="Run a robust fit",
    )

    combine_parallel = luigi.IntParameter(
        significant=False,
        description="Run the fits in parallel",
    )

    asimov_data = luigi.BoolParameter(
        default=True,
        significant=False,
        description="Use Asimov data for the fit",
    )

    mode = luigi.ChoiceParameter(
        choices=["exp", "obs"],
        default="exp",
        significant=True,
        description="Mode of the combine tool",
    )

    # upstream requirements
    reqs = Requirements(
        RemoteWorkflow.reqs,
        CreateDatacards=CreateDatacards,
        CreateWorkspace=CreateWorkspaceV2,
        GenToys=GenToysV2,
    )

    def workflow_requires(self):
        reqs = super().workflow_requires()

        reqs["workspace"] = self.reqs.CreateWorkspace.req(self)
        if self.mode == "exp":
            reqs["toy_file"] = self.reqs.GenToys.req(self)

        return reqs

    def requires(self):
        reqs = {
            "workspace": self.reqs.CreateWorkspace.req(self),
        }
        if self.mode == "exp":
            reqs["gen_toys"] = self.reqs.GenToys.req(self)
        return reqs

    def output(self):
        output_dict = {}
        output_dict[f"impacts_{self.mode}"] = self.target(f"impacts_{self.mode}.json")
        output_dict[f"impacts_{self.mode}_log"] = self.target(f"impacts_{self.mode}.log")
        return output_dict

    @property
    def impacts_name(self):
        name = f"impacts__m{self.mass}"
        return name

    def store_parts(self) -> law.util.InsertableDict:
        parts = super().store_parts()
        parts.insert_after("fit_v2", "impacts", self.impacts_name)
        return parts

    @law.decorator.log
    @law.decorator.safe_output
    def run(self):
        input_workspace = self.input()["workspace"]["workspace"].path
        if self.mode == "exp":
            input_toys = self.input()["gen_toys"]["toy_file"].path
        output_impact_file = self.output()[f"impacts_{self.mode}"].path
        output_dirname = os.path.dirname(output_impact_file) + "/"
        # touch output_dirname
        if not os.path.exists(output_dirname):
            os.makedirs(output_dirname)

        # base command
        command_base = "combineTool.py -M Impacts"
        command_base += f" -m {self.mass}"
        command_base += f" -d {input_workspace}"

        # do initial fit
        command_1 = command_base
        command_1 += f" --robustFit {self.robust_fit}"
        command_1 += " -t -1" if self.mode == "exp" else ""
        command_1 += f" --toysFile {input_toys}" if self.mode == "exp" else ""
        command_1 += " --doInitialFit"
        self.publish_message(f"running command: {command_1}")
        p_initial, out_initial = self.run_command(command_1, echo=True, cwd=output_dirname)

        # do impacts
        command_2 = command_base
        command_2 += f" --robustFit {self.robust_fit}"
        command_2 += " -t -1" if self.mode == "exp" else ""
        command_2 += f" --toysFile {input_toys}" if self.mode == "exp" else ""
        command_2 += " --doFits"
        command_2 += f" --parallel {self.combine_parallel}"
        self.publish_message(f"running command: {command_2}")
        p_impacts, out_impacts = self.run_command(command_2, echo=True, cwd=output_dirname)

        # collect impacts
        command_3 = command_base
        command_3 += f" -o {output_impact_file}"
        self.publish_message(f"running command: {command_3}")
        p_collect, out_collect = self.run_command(command_3, echo=True, cwd=output_dirname)

        # store all outputs in log file
        output = out_initial + out_impacts + out_collect
        self.output()[f"impacts_{self.mode}_log"].dump("\n".join(output), formatter="text")
