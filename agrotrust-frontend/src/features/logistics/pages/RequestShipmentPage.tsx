import { useNavigate, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRequestShipment } from "../hooks";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { numberInRange } from "@/lib/validation/shared";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";

const schema = z.object({
  pickup_lat: numberInRange({ min: -90, max: 90, message: "Latitude must be between -90 and 90" }),
  pickup_lon: numberInRange({ min: -180, max: 180, message: "Longitude must be between -180 and 180" }),
  dropoff_lat: numberInRange({ min: -90, max: 90, message: "Latitude must be between -90 and 90" }),
  dropoff_lon: numberInRange({ min: -180, max: 180, message: "Longitude must be between -180 and 180" }),
});
type FormValues = z.infer<typeof schema>;

export function RequestShipmentPage() {
  const { orderId = "" } = useParams();
  const navigate = useNavigate();
  const requestShipment = useRequestShipment();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    const shipment = await requestShipment.mutateAsync([
      {
        order_id: orderId,
        pickup_lat: Number(values.pickup_lat),
        pickup_lon: Number(values.pickup_lon),
        dropoff_lat: Number(values.dropoff_lat),
        dropoff_lon: Number(values.dropoff_lon),
      },
    ]);
    navigate(paths.shipmentDetail(shipment.id));
  };

  return (
    <div className="max-w-lg">
      <h1 className="mb-1 text-xl font-semibold text-foreground">Request a shipment</h1>
      <p className="mb-4 text-sm text-muted">For order {orderId.slice(0, 8)}</p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        {requestShipment.isError && (
          <Alert tone="danger">
            {requestShipment.error instanceof ApiError ? requestShipment.error.message : "Could not request a shipment."}
          </Alert>
        )}
        <div>
          <p className="mb-2 text-sm font-medium text-foreground">Pickup point</p>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Latitude" error={errors.pickup_lat?.message} {...register("pickup_lat")} />
            <Input label="Longitude" error={errors.pickup_lon?.message} {...register("pickup_lon")} />
          </div>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium text-foreground">Dropoff point</p>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Latitude" error={errors.dropoff_lat?.message} {...register("dropoff_lat")} />
            <Input label="Longitude" error={errors.dropoff_lon?.message} {...register("dropoff_lon")} />
          </div>
        </div>
        <Button type="submit" loading={isSubmitting} className="w-full">
          Request shipment
        </Button>
      </form>
    </div>
  );
}
