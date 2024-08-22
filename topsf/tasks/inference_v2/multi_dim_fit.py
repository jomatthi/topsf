# coding: utf-8

import luigi
import law
import os

from columnflow.tasks.framework.base import Requirements
from columnflow.tasks.framework.remote import RemoteWorkflow
from topsf.tasks.inference import CreateDatacards

from topsf.tasks.inference_v2.workspace import CreateWorkspaceV2
from topsf.tasks.inference_v2.run_combine import RunCombine
from topsf.tasks.inference_v2.gen_toys import GenToysV2


class MultiDimFitV2(
    RunCombine,
):
    cminSingleNuisFit = luigi.BoolParameter(  # FIXME Why does this parameter missing not cause an error?
        significant=False,
        description="Run a single nuisance fit for each channel",
    )

    cminFallbackAlgo = luigi.Parameter(
        significant=False,
        description="Fallback algorithm for the cminimizer",
    )

    algo = luigi.Parameter(
        significant=False,
        description="Algorithm to use for the fit",
    )

    save_fit_result = luigi.BoolParameter(
        default=True,
        significant=False,
        description="Save the fit results",
    )

    save_workspace = luigi.BoolParameter(
        default=True,
        significant=False,
        description="Save the workspace",
    )

    snapshot_name = luigi.Parameter(
        default="",
        significant=False,
        description="Name of the snapshot",
    )

    freeze_fit_parameters = law.CSVParameter(
        significant=False,
        description="Freeze parameters for the fit",
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
            reqs["toy_file"] = self.reqs.GenToys.req(self)
        return reqs

    @property
    def mdf_name(self):
        name = f"mdf__{self.mode}"
        return name

    def store_parts(self) -> law.util.InsertableDict:
        parts = super().store_parts()
        parts.insert_after("fit_v2", "gen_toys", self.mdf_name)
        return parts

    def output(self):
        output_dict = {
            f"mdf_{self.mode}_file": self.target(
                f"higgsCombine_{self.mode}.MultiDimFit.mH120.root",
            ),
            f"mdf_{self.mode}_frozen_file": self.target(
                f"higgsCombine_{self.mode}_frozen.MultiDimFit.mH120.root",
            ),
            f"fit_{self.mode}_result": self.target(
                f"multidimfit_{self.mode}.root",
            ),
            f"fit_{self.mode}_frozen_result": self.target(
                f"multidimfit_{self.mode}_frozen.root",
            ),
            f"mdf_{self.mode}_log": self.target(
                f"mdf_{self.mode}.log",
            ),
            f"mdf_{self.mode}_frozen_log": self.target(
                f"mdf_{self.mode}_frozen.log",
            ),
        }
        return output_dict

    @law.decorator.log
    @law.decorator.safe_output
    def run(self):
        # if self.mode == "exp":
        self.combine_method = "MultiDimFit"
        input_workspace = self.input()["workspace"]["workspace"].path
        frozen_sys_workspace = self.output()[f"mdf_{self.mode}_file"].path
        if self.mode == "exp":
            toy_file = self.input()["toy_file"]["toy_file"].path
        output_mdf_file = self.output()[f"mdf_{self.mode}_file"].path
        output_dirname = os.path.dirname(output_mdf_file) + "/"
        print(f"output_dirname: {output_dirname}")
        # touch output_dirname
        if not os.path.exists(output_dirname):
            os.makedirs(output_dirname)

        # perform fit
        command_1 = f"combine -M {self.combine_method}"
        command_1 += f" --toysFile {toy_file}" if self.mode == "exp" else ""
        command_1 += " -t -1" if self.asimov_data or self.mode == "exp" else ""
        command_1 += f" --algo {self.algo}" if len(str(self.algo)) else ""
        command_1 += " --saveFitResult" if self.save_fit_result else ""
        command_1 += " --saveWorkspace" if self.save_workspace else ""
        command_1 += " --cminSingleNuisFit" if self.cminSingleNuisFit else ""
        command_1 += f" --cminFallbackAlgo {self.cminFallbackAlgo}" if len(str(self.cminFallbackAlgo)) else ""  # noqa: E501
        command_1 += f" -v {self.combine_verbosity}" if self.combine_verbosity > 0 else ""
        command_1 += " -h" if self.combine_help else ""
        command = f"{command_1} --datacard {input_workspace} -n _{self.mode}"
        self.publish_message(f"running command: {command}")
        p_1, outp_1 = self.run_command(command, echo=True, cwd=output_dirname)

        self.output()[f"mdf_{self.mode}_log"].dump("\n".join(outp_1), formatter="text")

        # perform fit, with frozen systematics
        command_2 = command_1
        command_2 += " --freezeParameters allConstrainedNuisance"
        command_2 += " --snapshotName MultiDimFit"
        command = f"{command_2} --datacard {frozen_sys_workspace} -n _{self.mode}_frozen"
        self.publish_message(f"running command: {command}")
        p_2, outp_2 = self.run_command(command, echo=True, cwd=output_dirname)

        self.output()[f"mdf_{self.mode}_frozen_log"].dump("\n".join(outp_2), formatter="text")
