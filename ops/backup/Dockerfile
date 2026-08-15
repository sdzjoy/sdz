FROM alpine:3.21

RUN apk add --no-cache age bash coreutils openssh-client postgresql17-client rsync tar tzdata \
    && addgroup -g 10002 -S backup \
    && adduser -u 10002 -S -D -G backup backup \
    && mkdir -p /backups /home/backup/.ssh \
    && chown -R backup:backup /backups /home/backup

COPY --chown=backup:backup backup.sh restore.sh /usr/local/bin/
RUN chmod 0555 /usr/local/bin/backup.sh /usr/local/bin/restore.sh

USER backup
ENTRYPOINT ["/usr/local/bin/backup.sh"]

