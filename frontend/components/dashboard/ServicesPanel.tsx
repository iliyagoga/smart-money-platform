import { Stack, TablePagination, Typography } from "@mui/material";
import { usePagination } from "../../hooks/usePagination";
import type { ServiceStatus } from "../../lib/types";
import { Panel } from "../ui/Panel";
import { StatusDot } from "../ui/StatusDot";

export function ServicesPanel({ services }: { services: ServiceStatus[] }) {
  const healthyCount = services.filter((service) => service.status === "UP").length;
  const pagination = usePagination(services, 5);
  return (
    <Panel title="Сервисы" meta={`${healthyCount}/${services.length}`}>
      {pagination.visible.map((service) => (
        <Stack
          key={service.name}
          direction="row"
          spacing={1.5}
          sx={{ py: 1.5, borderBottom: 1, borderColor: "divider", alignItems: "center" }}
        >
          <StatusDot active={service.status === "UP"} />
          <Typography variant="body2" sx={{ flex: 1 }}>{service.name}</Typography>
          <Typography variant="caption" color="text.secondary">{service.status}</Typography>
        </Stack>
      ))}
      {services.length > 0 && <TablePagination component="div" {...pagination.paginationProps} />}
    </Panel>
  );
}
