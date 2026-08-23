package com.smartmoney.data.api;

import com.smartmoney.data.service.NotFoundException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import org.springframework.http.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import java.time.Instant;
import java.util.*;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(NotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(NotFoundException e) { return problem(HttpStatus.NOT_FOUND,e.getMessage()); }
    @ExceptionHandler({IllegalArgumentException.class, ConstraintViolationException.class})
    ResponseEntity<ProblemDetail> badRequest(Exception e) { return problem(HttpStatus.BAD_REQUEST,e.getMessage()); }
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalid(MethodArgumentNotValidException e) {
        String details=e.getBindingResult().getFieldErrors().stream().map(x->x.getField()+": "+x.getDefaultMessage()).reduce((a,b)->a+", "+b).orElse("Invalid request");
        return problem(HttpStatus.BAD_REQUEST,details);
    }
    private ResponseEntity<ProblemDetail> problem(HttpStatus status,String detail) {
        ProblemDetail p=ProblemDetail.forStatusAndDetail(status,detail); p.setProperty("timestamp", Instant.now()); return ResponseEntity.status(status).body(p);
    }
}
