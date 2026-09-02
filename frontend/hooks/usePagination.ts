"use client";

import { useEffect, useState } from "react";

export function usePagination<T>(items: T[], initialRowsPerPage = 10) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(initialRowsPerPage);
  useEffect(() => {
    const lastPage = Math.max(0, Math.ceil(items.length / rowsPerPage) - 1);
    if (page > lastPage) setPage(lastPage);
  }, [items.length, page, rowsPerPage]);
  return {
    page, rowsPerPage, setPage,
    visible: items.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage),
    paginationProps: {
      count: items.length, page, rowsPerPage, rowsPerPageOptions: [5, 10, 25, 50],
      labelRowsPerPage: "На странице",
      onPageChange: (_: unknown, value: number) => setPage(value),
      onRowsPerPageChange: (event: React.ChangeEvent<HTMLInputElement>) => { setRowsPerPage(Number(event.target.value)); setPage(0); },
    },
  };
}
