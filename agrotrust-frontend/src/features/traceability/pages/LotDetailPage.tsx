import { useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLot, useLotHistory, useRecordInspection, useRecordWeighing } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatMilli } from "@/lib/formatting/currency";
import { formatDateTime } from "@/lib/formatting/date";
import { numberInRange } from "@/lib/validation/shared";
import { ApiError } from "@/lib/api/errors";

const weighingSchema = z.object({
  gross_kg: numberInRange({ min: 0.001, message: "Enter the gross weight" }),
  tare_kg: numberInRange({ min: 0, message: "Enter the tare weight" }),
});
type WeighingForm = z.infer<typeof weighingSchema>;

const inspectionSchema = z.object({
  grade: z.enum(["A", "B", "C", "REJECT"]),
  passed: z.enum(["true", "false"]),
  moisture_pct: z.string().optional(),
  notes: z.string().optional(),
});
type InspectionForm = z.infer<typeof inspectionSchema>;

export function LotDetailPage() {
  const { lotId = "" } = useParams();
  const { data: lot, isLoading } = useLot(lotId);
  const { data: history, isLoading: historyLoading } = useLotHistory(lotId);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!lot) return <Alert tone="danger">That lot could not be found.</Alert>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Lot {lot.code}</h1>
        <Badge tone={lot.quality_grade === "REJECT" ? "danger" : "primary"}>{lot.quality_grade}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted">Quantity</dt>
            <dd className="font-medium text-foreground">{formatMilli(lot.quantity_milli, ` ${lot.unit}`)}</dd>
          </div>
          <div>
            <dt className="text-muted">Harvested</dt>
            <dd className="font-medium text-foreground">{formatDateTime(lot.harvest_date)}</dd>
          </div>
          {history && (
            <div>
              <dt className="text-muted">Custody chain</dt>
              <dd className={`font-medium ${history.chain_valid ? "text-success" : "text-danger"}`}>
                {history.chain_valid ? "Verified" : "Tampering detected"}
              </dd>
            </div>
          )}
        </dl>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <WeighingCard lotId={lotId} />
        <InspectionCard lotId={lotId} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Custody history</CardTitle>
        </CardHeader>
        {historyLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !history?.events.length ? (
          <p className="text-sm text-muted">No events recorded yet.</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {history.events.map((event) => (
              <li key={event.id} className="flex items-start gap-3 border-l-2 border-primary/30 pl-3">
                <div>
                  <p className="font-medium text-foreground">{event.event_type}</p>
                  <p className="text-sm text-muted">{formatDateTime(event.at)}</p>
                  {event.location_label && <p className="text-sm text-muted">{event.location_label}</p>}
                  {event.note && <p className="text-sm text-muted">{event.note}</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}

function WeighingCard({ lotId }: { lotId: string }) {
  const recordWeighing = useRecordWeighing(lotId);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<WeighingForm>({ resolver: zodResolver(weighingSchema) });

  const onSubmit = async (values: WeighingForm) => {
    await recordWeighing.mutateAsync({ gross_kg: Number(values.gross_kg), tare_kg: Number(values.tare_kg) });
    reset();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Record weighing</CardTitle>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3" noValidate>
        {recordWeighing.isError && (
          <Alert tone="danger">
            {recordWeighing.error instanceof ApiError ? recordWeighing.error.message : "Could not record weighing."}
          </Alert>
        )}
        <Input label="Gross weight (kg)" error={errors.gross_kg?.message} {...register("gross_kg")} />
        <Input label="Tare weight (kg)" error={errors.tare_kg?.message} {...register("tare_kg")} />
        <Button type="submit" loading={isSubmitting} size="sm">
          Record weighing
        </Button>
      </form>
    </Card>
  );
}

function InspectionCard({ lotId }: { lotId: string }) {
  const recordInspection = useRecordInspection(lotId);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InspectionForm>({ resolver: zodResolver(inspectionSchema), defaultValues: { passed: "true" } });

  const onSubmit = async (values: InspectionForm) => {
    await recordInspection.mutateAsync({
      grade: values.grade,
      passed: values.passed === "true",
      moisture_pct: values.moisture_pct ? Number(values.moisture_pct) : undefined,
      notes: values.notes,
    });
    reset();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Record inspection</CardTitle>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3" noValidate>
        {recordInspection.isError && (
          <Alert tone="danger">
            {recordInspection.error instanceof ApiError
              ? recordInspection.error.message
              : "Could not record inspection."}
          </Alert>
        )}
        <Select label="Grade" error={errors.grade?.message} defaultValue="" {...register("grade")}>
          <option value="" disabled>
            Select a grade
          </option>
          <option value="A">A</option>
          <option value="B">B</option>
          <option value="C">C</option>
          <option value="REJECT">Reject</option>
        </Select>
        <Select label="Passed" {...register("passed")}>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </Select>
        <Input label="Moisture % (optional)" error={errors.moisture_pct?.message} {...register("moisture_pct")} />
        <Input label="Notes (optional)" {...register("notes")} />
        <Button type="submit" loading={isSubmitting} size="sm">
          Record inspection
        </Button>
      </form>
    </Card>
  );
}
