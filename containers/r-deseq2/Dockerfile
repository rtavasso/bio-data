# Pinned R / Bioconductor image for saved R analyses run by
# .agents/skills/bio-research/scripts/r_analysis.py (docker run --rm --network none).
#   docker build -t colloquy-r-deseq2:bioc3.23 containers/r-deseq2
# The base is pinned by tag and multi-arch index digest (linux/amd64 and linux/arm64). Bioconductor
# 3.23 fixes the Bioconductor package versions and CRAN is a dated Posit Package Manager snapshot
# (CRAN_SNAPSHOT); the installed versions of every package below are
# printed to /opt/r-deseq2/versions.json at build time and recorded in docs/v3/receipts/r-deseq2-image.json.
# No entrypoint: r_analysis.py supplies `Rscript --vanilla SCRIPT.R ARGS`. Nothing here runs fetched code.
FROM bioconductor/bioconductor_docker:RELEASE_3_23-R-4.6.1@sha256:821dbf9ac119eac41f177531c7ca8fc7084c99c04eb218a1aa7f52cb63bad5d9
ARG CRAN_SNAPSHOT=https://p3m.dev/cran/__linux__/noble/2026-10-06
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 CRAN_SNAPSHOT=${CRAN_SNAPSHOT}
RUN Rscript -e 'options(Ncpus = max(1L, parallel::detectCores()), repos = c(CRAN = Sys.getenv("CRAN_SNAPSHOT"))); \
      BiocManager::install(c("DESeq2", "edgeR", "limma", "apeglm", "jsonlite", "readr"), ask = FALSE, update = FALSE); \
      pkgs <- c("DESeq2", "edgeR", "limma", "apeglm", "jsonlite", "readr", "BiocManager"); \
      missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]; \
      if (length(missing)) stop("not installed: ", paste(missing, collapse = ", ")); \
      dir.create("/opt/r-deseq2", showWarnings = FALSE); \
      v <- c(list(R = paste(R.version$major, R.version$minor, sep = "."), Bioconductor = as.character(BiocManager::version()), \
               CRAN_snapshot = Sys.getenv("CRAN_SNAPSHOT")), \
             setNames(lapply(pkgs, function(p) as.character(packageVersion(p))), pkgs)); \
      jsonlite::write_json(v, "/opt/r-deseq2/versions.json", auto_unbox = TRUE, pretty = TRUE)' \
 && rm -rf /tmp/Rtmp* /tmp/downloaded_packages
LABEL org.opencontainers.image.title="colloquy-r-deseq2" \
      org.opencontainers.image.description="R 4.6.1 + Bioconductor 3.23: DESeq2, edgeR, limma, apeglm, jsonlite, readr"
