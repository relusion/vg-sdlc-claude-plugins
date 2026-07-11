export type AccountStatus = "active" | "disabled";

export type Account = {
  id: string;
  email: string;
  status: AccountStatus;
};

export function serializeAccount(row: Account): Account {
  return {
    id: row.id,
    email: row.email,
    status: row.status,
  };
}

export function canLogin(status: AccountStatus): boolean {
  return status === "active";
}
