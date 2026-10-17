# Keep the publisher's database and entrypoint; start directly as its existing user.
# The unused root-switching helper embeds an outdated Go standard library.
FROM postgres:18.6-alpine3.24@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873
USER root
RUN rm /usr/local/bin/gosu
USER postgres
