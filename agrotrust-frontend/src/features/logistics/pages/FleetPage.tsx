import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMyOrganizations } from "@/features/organizations/hooks";
import { useDrivers, useRegisterDriver, useRegisterVehicle, useVehicles } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { numberInRange } from "@/lib/validation/shared";
import { ApiError } from "@/lib/api/errors";

const vehicleSchema = z.object({
  plate: z.string().min(3, "Enter a plate number"),
  vehicle_type: z.string().min(1, "Pick a vehicle type"),
  capacity_kg: numberInRange({ min: 1, message: "Capacity must be greater than 0" }),
});
type VehicleForm = z.infer<typeof vehicleSchema>;

const driverSchema = z.object({
  name: z.string().min(2, "Enter the driver's name"),
  phone: z.string().min(8, "Enter a valid phone number"),
});
type DriverForm = z.infer<typeof driverSchema>;

export function FleetPage() {
  const { data: orgs, isLoading: orgsLoading } = useMyOrganizations();
  const logisticsOrg = orgs?.find((o) => o.type === "LOGISTICS");

  if (orgsLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  if (!logisticsOrg) {
    return (
      <EmptyState
        title="No logistics organization yet"
        description="Fleet and driver records belong to a logistics organization. Create one from the Organizations screen before registering vehicles."
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">Fleet for {logisticsOrg.name}</h1>
      <div className="grid gap-6 md:grid-cols-2">
        <VehiclesSection orgId={logisticsOrg.id} />
        <DriversSection orgId={logisticsOrg.id} />
      </div>
    </div>
  );
}

function VehiclesSection({ orgId }: { orgId: string }) {
  const { data: vehicles, isLoading } = useVehicles(orgId);
  const registerVehicle = useRegisterVehicle();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<VehicleForm>({ resolver: zodResolver(vehicleSchema) });

  const onSubmit = async (values: VehicleForm) => {
    await registerVehicle.mutateAsync({
      org_id: orgId,
      plate: values.plate,
      vehicle_type: values.vehicle_type,
      capacity_kg: Number(values.capacity_kg),
    });
    reset();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Vehicles</CardTitle>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)} className="mb-4 flex flex-col gap-3" noValidate>
        {registerVehicle.isError && (
          <Alert tone="danger">
            {registerVehicle.error instanceof ApiError ? registerVehicle.error.message : "Could not register the vehicle."}
          </Alert>
        )}
        <Input label="Plate number" placeholder="ABC123XY" error={errors.plate?.message} {...register("plate")} />
        <Select label="Vehicle type" error={errors.vehicle_type?.message} defaultValue="" {...register("vehicle_type")}>
          <option value="" disabled>
            Select a type
          </option>
          <option value="TRUCK">Truck</option>
          <option value="VAN">Van</option>
          <option value="PICKUP">Pickup</option>
          <option value="MOTORCYCLE">Motorcycle</option>
        </Select>
        <Input
          label="Capacity (kg)"
          error={errors.capacity_kg?.message}
          {...register("capacity_kg")}
        />
        <Button type="submit" loading={isSubmitting} size="sm">
          Register vehicle
        </Button>
      </form>
      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : vehicles && vehicles.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {vehicles.map((v) => (
            <li key={v.id} className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm">
              <span className="font-medium text-foreground">{v.plate}</span>
              <span className="text-muted">
                {v.vehicle_type} &middot; {v.capacity_kg.toLocaleString()} kg
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">No vehicles registered yet.</p>
      )}
    </Card>
  );
}

function DriversSection({ orgId }: { orgId: string }) {
  const { data: drivers, isLoading } = useDrivers(orgId);
  const registerDriver = useRegisterDriver();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<DriverForm>({ resolver: zodResolver(driverSchema) });

  const onSubmit = async (values: DriverForm) => {
    await registerDriver.mutateAsync({ org_id: orgId, name: values.name, phone: values.phone });
    reset();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Drivers</CardTitle>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)} className="mb-4 flex flex-col gap-3" noValidate>
        {registerDriver.isError && (
          <Alert tone="danger">
            {registerDriver.error instanceof ApiError ? registerDriver.error.message : "Could not register the driver."}
          </Alert>
        )}
        <Input label="Full name" error={errors.name?.message} {...register("name")} />
        <Input label="Phone number" placeholder="+234..." error={errors.phone?.message} {...register("phone")} />
        <Button type="submit" loading={isSubmitting} size="sm">
          Register driver
        </Button>
      </form>
      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : drivers && drivers.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {drivers.map((d) => (
            <li key={d.id} className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm">
              <span className="font-medium text-foreground">{d.name}</span>
              <span className="text-muted">{d.phone}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">No drivers registered yet.</p>
      )}
    </Card>
  );
}
