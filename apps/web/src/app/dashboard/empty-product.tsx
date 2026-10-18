import { Card, CardDescription, CardTitle } from "@/components/ui/card";

import { RegisterRepositoryForm } from "./register-form";

export function EmptyProduct() {
  return (
    <Card className="max-w-2xl">
      <CardTitle>Register your product</CardTitle>
      <CardDescription>
        Each workspace tracks one open-source product through its public GitHub repository.
      </CardDescription>
      <div className="mt-5">
        <RegisterRepositoryForm />
      </div>
    </Card>
  );
}
