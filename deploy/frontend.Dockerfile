FROM node:20-alpine AS build

ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL} \
    GENERATE_SOURCEMAP=false \
    DISABLE_ESLINT_PLUGIN=true \
    NODE_OPTIONS=--max-old-space-size=3072 \
    CI=true

WORKDIR /app/frontend
# yarn.lock opsional (beberapa push GitHub tidak menyertakannya): glob [k] tidak gagal bila tidak ada.
COPY frontend/package.json frontend/yarn.loc[k] ./
RUN if [ -f yarn.lock ]; then yarn install --frozen-lockfile --network-timeout 600000; \
    else yarn install --network-timeout 600000; fi

COPY frontend/ ./
RUN yarn build

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/build /usr/share/nginx/html
EXPOSE 80
