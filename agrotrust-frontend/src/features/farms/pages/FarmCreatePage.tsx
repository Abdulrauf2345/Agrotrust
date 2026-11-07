import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useCreateFarm } from "../hooks";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { numberInRange } from "@/lib/validation/shared";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";

const schema = z.object({
  name: z.string().min(2, "Enter a farm name"),
  state: z.string().min(1, "State is required"),
  lga: z.string().min(1, "LGA is required"),
  size_hectares: numberInRange({ min: 0.01, message: "Size must be greater than 0" }),
  lat: numberInRange({ min: -90, max: 90, message: "Latitude must be between -90 and 90" }),
  lon: numberInRange({ min: -180, max: 180, message: "Longitude must be between -180 and 180" }),
});
type FormValues = z.infer<typeof schema>;

export function FarmCreatePage() {
  const navigate = useNavigate();
  const createFarm = useCreateFarm();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    const farm = await createFarm.mutateAsync({
      name: values.name,
      state: values.state,
      lga: values.lga,
      size_hectares: Number(values.size_hectares),
      lat: Number(values.lat),
      lon: Number(values.lon),
    });
    navigate(paths.farmDetail(farm.id));
  };

  return (
    <div className="max-w-lg">
      <h1 className="mb-4 text-xl font-semibold text-foreground">Register a farm</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        {createFarm.isError && (
          <Alert tone="danger">
            {createFarm.error instanceof ApiError ? createFarm.error.message : "Could not register the farm."}
          </Alert>
        )}
        <Input label="Farm name" error={errors.name?.message} {...register("name")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="State" error={errors.state?.message} {...register("state")} />
          <Input label="LGA" error={errors.lga?.message} {...register("lga")} />
        </div>
        <Input label="Size (hectares)" error={errors.size_hectares?.message} {...register("size_hectares")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Latitude" error={errors.lat?.message} {...register("lat")} />
          <Input label="Longitude" error={errors.lon?.message} {...register("lon")} />
        </div>
        <Button type="submit" loading={isSubmitting} className="w-full">
          Register farm
        </Button>
      </form>
    </div>
  );
}
