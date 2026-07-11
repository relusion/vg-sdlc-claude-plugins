import { Router } from "express";
import { requireProjectRole, type ProjectRole } from "../auth/permissions";

type RequestWithAuth = {
  params: { projectId: string };
  actor: { id: string; projectRole: ProjectRole };
};

export const router = Router();

export async function deleteProject(projectId: string): Promise<void> {
  await Promise.resolve(projectId);
}

router.delete("/projects/:projectId", async (req, res, next) => {
  try {
    const request = req as unknown as RequestWithAuth;
    requireProjectRole(request.actor.projectRole, "owner");
    await deleteProject(request.params.projectId);
    res.status(204).send();
  } catch (err) {
    next(err);
  }
});
