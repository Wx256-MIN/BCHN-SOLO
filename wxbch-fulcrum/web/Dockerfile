FROM nginx:alpine
RUN apk add --no-cache gettext
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY entrypoint.sh /entrypoint.sh
COPY index.html /usr/share/nginx/html/index.html
COPY manifest.webmanifest icon-192.png icon-512.png apple-touch-icon.png /usr/share/nginx/html/
RUN chmod 0755 /entrypoint.sh
EXPOSE 3001
ENTRYPOINT ["/entrypoint.sh"]
