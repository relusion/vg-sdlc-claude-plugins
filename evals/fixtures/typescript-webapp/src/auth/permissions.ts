export type ProjectRole = "viewer" | "editor" | "owner";

const roleRank: Record<ProjectRole, number> = {
  viewer: 1,
  editor: 2,
  owner: 3,
};

export function requireProjectRole(actorRole: ProjectRole, required: ProjectRole): void {
  if (roleRank[actorRole] < roleRank[required]) {
    const err = new Error("forbidden");
    (err as Error & { status?: number }).status = 403;
    throw err;
  }
}
